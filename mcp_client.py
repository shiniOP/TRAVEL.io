import os
import sys
from pathlib import Path
from typing import Any

import certifi
from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP
from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_groq import ChatGroq


# ============================================================
# ENVIRONMENT
# ============================================================

load_dotenv(override=True)

# SSL certificate configuration
# This helps avoid SSL certificate/path issues on some systems.
os.environ["SSL_CERT_FILE"] = certifi.where()
os.environ["REQUESTS_CA_BUNDLE"] = certifi.where()


AVIATION_STACK_API_KEY = os.getenv(
    "AVIATIONSTACK_API_KEY"
)

TAVILY_API_KEY = os.getenv(
    "TAVILY_API_KEY"
)

OPENWEATHER_API_KEY = os.getenv(
    "OPENWEATHER_API_KEY"
)

GROQ_API_KEY = os.getenv(
    "GROQ_API_KEY"
)


# ============================================================
# GEMINI LLM
# ============================================================

if not GROQ_API_KEY:
    raise ValueError(
        "GEMINI_API_KEY is missing from .env"
    )


llm = ChatGroq(
    model="llama-3.3-70b-versatile",
    api_key=os.getenv("GROQ_API_KEY"),
)

# ============================================================
# WEATHER MCP SERVER PATH
# ============================================================

BASE_DIR = Path(__file__).resolve().parent

WEATHER_SERVER_PATH = (
    BASE_DIR / "custom_weather_mcp_server.py"
)


# ============================================================
# WEATHER ENVIRONMENT
# ============================================================

WEATHER_ENV = {
    "OPENWEATHER_API_KEY": OPENWEATHER_API_KEY
}


# ============================================================
# MCP CLIENT
# ============================================================

client = MultiServerMCPClient(
    {

        # ----------------------------------------------------
        # 1. REMOTE MCP - TAVILY
        # ----------------------------------------------------

        "tavily": {
            "transport": "streamable_http",

            "url": (
                "https://mcp.tavily.com/mcp/"
                f"?tavilyApiKey={TAVILY_API_KEY}"
            ),
        },


        # ----------------------------------------------------
        # 2. LOCAL MCP - AVIATIONSTACK
        # ----------------------------------------------------

    "aviationstack": {
    "transport": "stdio",
    "command": "uvx",
    "args": [
        "--with",
        "mcp==1.27.2",
        "aviationstack-mcp"
    ],
    "env": {
        "AVIATION_STACK_API_KEY": AVIATION_STACK_API_KEY
    },
},

        # ----------------------------------------------------
        # 3. CUSTOM MCP - WEATHER
        # ----------------------------------------------------

        "weather": {

            "transport": "stdio",

            # Use the same Python environment
            # that is running this application.
            "command": sys.executable,

            # Run our custom weather MCP server.
            "args": [
                str(WEATHER_SERVER_PATH)
            ],

            "env": WEATHER_ENV,
        },
    }
)


# ============================================================
# GET ALL MCP TOOLS
# ============================================================

async def get_all_tools():

    tools = await client.get_tools()

    print("\nAvailable MCP Tools:\n")

    for tool in tools:
        print(tool.name)

    return tools


# ============================================================
# TAVILY TOOL
# ============================================================

tavily_search_tool = None


async def get_tavily_search_tool():

    global tavily_search_tool

    if tavily_search_tool is not None:
        return tavily_search_tool

    tools = await client.get_tools(
        server_name="tavily"
    )

    print("\nAvailable Tavily Tools:\n")

    for tool in tools:
        print(tool.name)

    tavily_search_tool = next(
        (
            tool
            for tool in tools
            if tool.name == "tavily_search"
        ),
        None
    )

    if tavily_search_tool is None:
        raise RuntimeError(
            "Tavily search tool was not found."
        )

    return tavily_search_tool


# ============================================================
# TAVILY SEARCH
# ============================================================

async def tavily_mcp_search(query: str):

    tool = await get_tavily_search_tool()

    result = await tool.ainvoke(
        {
            "query": query
        }
    )

    return result


# ============================================================
# AVIATION TOOLS
# ============================================================

aviation_tools = {}


async def get_aviation_tools():

    global aviation_tools

    if aviation_tools:
        return aviation_tools

    tools = await client.get_tools(
        server_name="aviationstack"
    )

    print("\nAvailable AviationStack Tools:\n")

    for tool in tools:
        print(tool.name)

    aviation_tools = {
        tool.name: tool
        for tool in tools
    }

    return aviation_tools


# ============================================================
# AVIATION MCP CALL
# ============================================================

async def aviation_mcp_call(
    tool_name: str,
    tool_args: dict[str, Any] | None = None,
):

    tools = await get_aviation_tools()

    tool = tools.get(tool_name)

    if tool is None:

        available_tools = ", ".join(
            tools.keys()
        )

        raise RuntimeError(
            f"Aviation tool '{tool_name}' "
            f"was not found. "
            f"Available tools: "
            f"{available_tools or 'none'}"
        )

    return await tool.ainvoke(
        tool_args or {}
    )


# ============================================================
# WEATHER TOOLS
# ============================================================

weather_tool = None
forecast_tool = None


async def initialize_weather_tools():

    global weather_tool
    global forecast_tool

    # Already initialized
    if (
        weather_tool is not None
        and forecast_tool is not None
    ):
        return


    # --------------------------------------------------------
    # Check weather MCP server file
    # --------------------------------------------------------

    if not WEATHER_SERVER_PATH.exists():

        raise FileNotFoundError(
            "Weather MCP server file was not found: "
            f"{WEATHER_SERVER_PATH}"
        )


    # --------------------------------------------------------
    # Get only Weather MCP tools
    # --------------------------------------------------------

    tools = await client.get_tools(
        server_name="weather"
    )

    tools_by_name = {
        tool.name: tool
        for tool in tools
    }


    # --------------------------------------------------------
    # Find required tools
    # --------------------------------------------------------

    weather_tool = tools_by_name.get(
        "get_current_weather"
    )

    forecast_tool = tools_by_name.get(
        "get_forecast"
    )


    # --------------------------------------------------------
    # Check missing tools
    # --------------------------------------------------------

    missing_tools = []

    if weather_tool is None:
        missing_tools.append(
            "get_current_weather"
        )

    if forecast_tool is None:
        missing_tools.append(
            "get_forecast"
        )

    if missing_tools:

        available_tools = ", ".join(
            tools_by_name.keys()
        )

        raise RuntimeError(
            "Missing Weather MCP tools: "
            f"{', '.join(missing_tools)}. "
            f"Available tools: "
            f"{available_tools or 'none'}"
        )


# ============================================================
# CURRENT WEATHER
# ============================================================

async def weather_mcp_search(
    city: str
):

    await initialize_weather_tools()

    result = await weather_tool.ainvoke(
        {
            "city": city
        }
    )

    return result


# ============================================================
# WEATHER FORECAST
# ============================================================

async def forecast_mcp_search(
    city: str
):

    await initialize_weather_tools()

    result = await forecast_tool.ainvoke(
        {
            "city": city
        }
    )

    return result


# ============================================================
# DESTINATION EXTRACTOR
# ============================================================

def extract_destination(
    query: str
):

    prompt = f"""
Extract only the destination city or country
from the following travel query.

Query:
{query}

Return only the destination name.
Do not add explanations.
"""

    response = llm.invoke(
        prompt
    )

    return str(
        response.content
    ).strip()