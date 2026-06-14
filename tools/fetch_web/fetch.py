from .client import FetchWebAgent
import json
from langchain.tools import tool

fetchWebAgent = FetchWebAgent()
@tool
def fetch_web(query):
    "通过调用子Agent来查询/获取网页信息"
    return fetchWebAgent.run(query)