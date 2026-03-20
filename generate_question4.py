import logging
from langchain_community.llms.xinference import Xinference
from langchain_community.llms.ollama import Ollama
from langchain.prompts import PromptTemplate
from langchain.chains import LLMChain
from fastapi import FastAPI, HTTPException
from langchain_core.pydantic_v1 import BaseModel, Field
import json
from langchain_core.output_parsers import JsonOutputParser
import re

# Configure logging
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')

app = FastAPI()

# "generate_options": "{'A': '队列'}, {'B': '栈'}, {'C': '链表'}, {'D': '数组'}",

json_example = '''
{
    "choice_questions": [
        {
            "generate_question": "以下哪种数据结构是LIFO (后进先出)？",
            "generate_options": "[{'A': '队列'}, {'B': '栈'}, {'C': '链表'}, {'D': '数组'}]",
            "generate_standard_answer": "B",
            "explanation": "栈（Stack）是一种后进先出（LIFO）的数据结构，这意味着最后一个入栈的元素将最先出栈。"
        }
    ],
    "fill_in_the_blank_questions": [
        {
            "generate_question": "在计算机科学中，算法的时间复杂度通常使用_____符号来表示。",
            "generate_standard_answer": "大O",
            "explanation": "大O符号（Big-O Notation）用于描述算法的时间复杂度，表示算法的运行时间与输入数据规模之间的关系。"
        }
    ],
    "subjective_questions": [
        {
            "generate_question": "请简述操作系统中进程和线程的区别。",
            "generate_standard_answer": "进程是操作系统分配资源的基本单位，线程是CPU调度和执行的基本单位。进程有独立的地址空间，而线程共享进程的地址空间。",
            "explanation": "进程是一个独立的程序运行实例，具有独立的内存空间，而线程是在进程内执行的多个任务，它们共享进程的资源。线程比进程更轻量，切换的开销也更小。"
        }
    ]
}'''


# 定义题目的格式
class Question(BaseModel):
    generate_question: str
    generate_options: list[str] = Field(default_factory=list)
    generate_standard_answer: str
    explanation: str


# 定义整体返回的格式
class TestPaper(BaseModel):
    choice_questions: list[Question] = Field(default_factory=list)
    # one_choice_questions: list[Question] = Field(default_factory=list)
    fill_in_the_blank_questions: list[Question] = Field(default_factory=list)
    subjective_questions: list[Question] = Field(default_factory=list)


from pydantic import BaseModel


class SubjectiveJudgmentRequest(BaseModel):
    subjective_question: str
    student_answer: str
    standard_answer: str


class StageGenerateRequest(BaseModel):
    query: str
    kb_name: str
    choice: int

# model = "qwen2.5:7b"
model = "qwen2-instruct"

@app.post("/stage_generate_question/")
def stage_generate_question(request: StageGenerateRequest):
    query, kb_name, choice = request.query, request.kb_name, request.choice
    category = "简答题" if choice else "选择题"
    try:
        logging.info(
            f"Received request for generating questions with query: {query}, kb_name: {kb_name}, category: {category}")

        import openai
        rag_base_url = f"http://82.156.232.115:7864/knowledge_base/local_kb/{kb_name}"
        data = {
            "model": model,
            "messages": [
                {"role": "user", "content": "你好"},
                {"role": "assistant", "content": "你好，我是人工智能大模型"},
                {"role": "user", "content": f"关于{query}的考试试卷题目"},
            ],
            "stream": False,
            "temperature": 0,
            "extra_body": {
                "top_k": 5,
                "score_threshold": 2.0,
                "return_direct": True,
            }
        }

        logging.debug(f"Sending request to RAG service with URL: {rag_base_url} and data: {data}")
        client = openai.Client(base_url=rag_base_url, api_key="EMPTY")
        resp = client.chat.completions.create(**data)
        resp = json.loads(resp)
        logging.debug(f"Received response: {resp}")

        context = resp['docs']
        logging.info(f"Extracted context from RAG response: {context}")

        llm = Xinference(server_url="http://82.156.232.115:9000", model_uid="qwen2-instruct")
        # llm = Ollama(model="qwen2.5:7b")
        prompt = PromptTemplate(
            input_variables=['json_example', 'context', 'query', 'category'],
            template='''1.你现在扮演一个计算机专业的大学老师。
                    2.从专业的角度，参考上下文中提供的试卷样例的出题格式和出题风格，生成一份课堂小测的题目。
                    3.可以包含的题型有选择题、填空题、主观题。
                    4.请你返回一个json格式的字典，选择题的键分别为generate_question,generate_options, generate_standard_answer，
                    填空题和主观题的键分别为generate_question,generate_standard_answer,explanation。
                    5.json格式例子：{json_example}。

                    上下文：{context}。

                    请你生成三道关于{query}的课堂小测题目，题型为{category}''')

        # logging.info(f"Creating LLMChain with prompt: {prompt}")
        chains = LLMChain(prompt=prompt, llm=llm)

        generated = chains.run(json_example=json_example, context=context, query=query, category=category)
        logging.debug(f"Generated question set: {generated}")
        print(1111111111111111111111111111111111111111)

        parser = JsonOutputParser(model=TestPaper)
        ###
        print(2)
        parsed_result = parser.parse(generated)
        print(3)
        logging.info(f"Parsed test paper result: {parsed_result}")
        print(4)
        key = 'subjective_questions' if choice else 'choice_questions'
        result = parsed_result[key][0]
        print(5)
        return result

    except Exception as e:
        logging.error(f"Error generating question: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/subjective_judgment/")
def subjective_judgment(request: SubjectiveJudgmentRequest):
    subjective_question = request.subjective_question
    student_answer = request.student_answer
    standard_answer = request.standard_answer
    try:
        logging.info(f"Received request for subjective judgment with question: {subjective_question}")

        llm = Xinference(server_url="http://207ai.top:9000", model_uid="qwen2-instruct", temperature=0)
        # llm = Ollama(model="qwen2.5:7b")
        prompt = PromptTemplate(
            input_variables=['subjective_question', 'student_answer', 'standard_answer'],
            template='''你是一名资深教师助理，负责帮助老师批改和评分学生提交的主观题答案。这些题目主要涉及算法流程分析、概念性问答、以及如何选择合适的算法等内容。你将根据以下六个评分标准，对学生的答案进行评估和打分。请确保你的评估详细且准确，并在最后提供总分。评分标准如下：

1. **准确性**（0-5分）：
   - 根据学生对问题的理解和回答的准确程度进行评分。如果答案完全正确，描述了算法或概念的关键要点，并且算法选择合理，得5分。如果存在小错误、偏离题意的地方或算法选择不当，视其严重程度扣分。完全错误或无关答案得0分。

2. **逻辑性**（0-5分）：
   - 根据学生答案的逻辑结构、推理过程以及算法流程的清晰度进行评分。如果答案逻辑严密，推理过程清晰且算法步骤明确，得5分。如果逻辑混乱，推理不连贯或算法流程描述不清，视其严重程度扣分。没有逻辑或推理过程的答案得0分。

3. **表达清晰度**（0-5分）：
   - 根据学生表达的清晰度和语言的准确性进行评分。如果表达流畅、语言精准且无语法错误，术语使用正确，得5分。如果存在表达不清、语法错误或术语使用不当，视其严重程度扣分。表达不清或充满错误的答案得0分。

4. **深度分析**（0-5分）：
   - 根据学生对算法或概念的深入分析和理解进行评分。如果学生能提供超出题目要求的深入见解、分析算法的优缺点，或对算法选择进行了全面的讨论，得5分。如果答案只是表面分析，缺乏深度或未能充分考虑算法选择的合理性，视其程度扣分。缺乏任何分析的答案得0分。

5. **创新性**（0-5分）：
   - 根据学生答案的独特性和创新性进行评分。如果学生能提出新颖的算法改进、独特的概念理解，或提供有创意的解决方案，得5分。如果答案中规中矩，缺乏创新，视其程度扣分。完全缺乏创新的答案得0分。

6. **完整性**（0-5分）：
   - 根据学生回答是否涵盖了题目要求的所有方面，并提供了全面的分析或算法流程进行评分。如果答案非常全面，涵盖了所有必要的要点，并对问题进行了完整的回答，得5分。如果有些要点未涵盖或有重要内容遗漏，视其程度扣分。严重不完整的答案得0分。

请根据以上评分标准和老师提供的标准答案，详细评估以下学生的答案，并分别给出每个评分标准的具体得分与评分理由。最后，计算并提供该学生答案的总分。

学生的主观题题目：
{subjective_question}
学生的答案：
{student_answer}
老师提供的标准答案：
{standard_answer}
请对上述学生的答案进行详细的评估，并分别对每个标准进行打分（0-5分），同时给出具体的评分理由，并将所有项目得分相加，得出该学生答案的总分数。'''
        )

        logging.info(f"Creating LLMChain for subjective judgment")
        chains = LLMChain(prompt=prompt, llm=llm)

        generated = chains.run(subjective_question=subjective_question, student_answer=student_answer,
                               standard_answer=standard_answer)
        logging.debug(f"Generated subjective judgment result: {generated}")

        # 提取最后一串数字作为总分
        total_score = re.findall(r'=\s*(\d+)', generated)

        if total_score == None:
            total_sore = re.findall(r'\d+', generated)[-1]
        else:
            total_score = total_score[-1]

        return {"total_score": total_score}

    except Exception as e:
        logging.error(f"Error in subjective judgment: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    pass
    # a = stage_generate_question("大模型技术", "samples")
    subjective_judgment("Linux操作系统有哪些特点？", '''Linux操作系统具有以下几个特点：
        开源与自由：Linux 是一个开源操作系统，任何人都可以自由地查看、修改和分发其源代码。这使得开发者和用户可以根据自己的需求定制操作系统。
        多用户、多任务：Linux 支持多用户环境，多个用户可以同时登录并使用系统。此外，Linux 还支持多任务处理，可以同时运行多个程序而互不干扰。
        高稳定性和安全性：Linux 以其稳定性著称，适合长时间运行而无需重启。由于其内核和权限管理的设计，Linux 在安全性方面也表现出色。
        广泛的硬件支持：Linux 支持多种硬件平台，包括服务器、桌面电脑、嵌入式设备等，适用于各种场景。
        强大的网络功能：Linux 提供了丰富的网络功能，适用于服务器和网络设备的操作，且支持多种网络协议。
        丰富的命令行工具：Linux 提供了大量的命令行工具，适合进行系统管理、编程、文件处理等多种任务，尤其适合高级用户和开发者使用。
        社区支持：Linux 拥有庞大的用户和开发者社区，提供丰富的文档和支持，用户遇到问题时可以得到及时的帮助。
        多种发行版：Linux 有许多不同的发行版，如 Ubuntu、CentOS、Debian 等，用户可以根据自己的需求选择合适的版本。''', '''1. 开放性的系统
        2. 多用户多任务的系统
        3. 具有出色的速度性能和稳定性
        4. 提供了良好的用户界面
        5. 提供了丰富的网络功能
        6. 具有可靠的系统安全性
        7.标准兼容性和可移植性''')
