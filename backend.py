import os
import asyncio
import json
import operator
import uuid
from typing import Any, Annotated, TypedDict

import certifi
import psycopg
from dotenv import load_dotenv
from psycopg.rows import dict_row

from langchain_core.messages import (
    AnyMessage,
    HumanMessage,
    AIMessage,
    SystemMessage,
)

from langchain_groq import ChatGroq
from langgraph.graph import StateGraph, START, END
from langgraph.types import Command, interrupt
from langgraph.checkpoint.postgres import PostgresSaver

from mcp_client import (
    extract_destination,
    tavily_mcp_search,
    aviation_mcp_call,
    weather_mcp_search,
    forecast_mcp_search,
)

# Environment
load_dotenv(override=True)

# to prevent SSL certificate path issues
os.environ["SSL_CERT_FILE"] = certifi.where()
os.environ["REQUESTS_CA_BUNDLE"] = certifi.where()

GROQ_API_KEY = os.getenv("GROQ_API_KEY")

if not GROQ_API_KEY:
    raise ValueError("GROQ_API_KEY is missing from .env")

llm = ChatGroq(
    model="llama-3.3-70b-versatile",
    api_key=os.getenv("GROQ_API_KEY"),
)


def get_database_url():
    database_url = os.getenv("DATABASE_URL")

    if not database_url:
        raise ValueError(
            "DATABASE_URL is missing. Please add your PostgreSQL URL to .env"
        )

    if "sslmode=" not in database_url:
        separator = "&" if "?" in database_url else "?"
        database_url = f"{database_url}{separator}sslmode=require"

    return database_url


# State
class TravelState(TypedDict):
    messages: Annotated[list[AnyMessage], operator.add]
    user_query: str

    guardrail_allowed: bool
    guardrail_reason: str

    selected_agents: list[str]
    supervisor_reasoning: str
    trip_constraints: dict[str, Any]

    flight_results: str
    hotel_results: str
    weather_results: str
    budget_results: str
    itinerary: str

    approval_request: str
    approved: bool
    human_feedback: str

    final_response: str
    llm_calls: int


AGENT_ORDER = [
    "flight_agent",
    "hotel_agent",
    "weather_agent",
    "budget_agent",
    "itinerary_agent",
]


def empty_constraints():
    return {
        "destination": "",
        "origin": "",
        "duration": "",
        "budget": "",
        "travel_style": "",
        "special_preferences": [],
    }


def ask_llm(system_prompt: str, user_prompt: str):
    response = llm.invoke([
        SystemMessage(content=system_prompt),
        HumanMessage(content=user_prompt),
    ])
    return str(response.content)


def parse_json(text: str):
    start = text.find("{")
    end = text.rfind("}")

    if start == -1 or end == -1:
        raise ValueError("The model did not return valid JSON.")

    return json.loads(text[start:end + 1])


# Guardrail + Supervisor
def supervisor_agent(state: TravelState):
    query = state["user_query"]
    llm_calls = state.get("llm_calls", 0)

    guardrail_prompt = f"""
Decide whether this request is related to travel planning.

Travel requests can involve flights, hotels, destinations,
weather, budgets, transportation, sightseeing, visas,
restaurants and itineraries.

Block unrelated, harmful or illegal requests.

Return JSON only:

{{
    "allowed": true,
    "reason": ""
}}

User request:
{query}
"""

    try:
        raw = ask_llm(
            "You are the input guardrail for a travel application.",
            guardrail_prompt,
        )
        result = parse_json(raw)

        allowed = bool(result.get("allowed", True))
        reason = str(result.get("reason", "")).strip()
        llm_calls += 1

    except Exception as e:
        print(f"Guardrail fallback used: {e}")
        allowed = True
        reason = "Guardrail validation was unavailable."

    if not allowed:
        message = reason or "TRAVEL.io can only help with travel-related requests."

        return {
            "guardrail_allowed": False,
            "guardrail_reason": message,
            "selected_agents": [],
            "trip_constraints": empty_constraints(),
            "supervisor_reasoning": message,
            "final_response": message,
            "messages": [AIMessage(content=message)],
            "llm_calls": llm_calls,
        }

    supervisor_prompt = f"""
You are the supervisor of a travel-planning multi-agent system.

Available agents:

flight_agent - flights, airports and airlines
hotel_agent - hotels and accommodation
weather_agent - weather and forecasts
budget_agent - trip cost and budget analysis
itinerary_agent - creates the final itinerary

Select only the agents needed for the request.
The itinerary_agent must always be selected.

Return JSON only:

{{
    "selected_agents": [],
    "trip_constraints": {{
        "destination": "",
        "origin": "",
        "duration": "",
        "budget": "",
        "travel_style": "",
        "special_preferences": []
    }},
    "reasoning": ""
}}

User request:
{query}
"""

    try:
        raw = ask_llm(
            "You are the supervisor of TRAVEL.io.",
            supervisor_prompt,
        )
        result = parse_json(raw)

        requested_agents = result.get("selected_agents", [])

        selected_agents = [
            agent for agent in AGENT_ORDER
            if agent in requested_agents
        ]

        if "itinerary_agent" not in selected_agents:
            selected_agents.append("itinerary_agent")

        constraints = empty_constraints()

        if isinstance(result.get("trip_constraints"), dict):
            constraints.update(result["trip_constraints"])

        reasoning = str(result.get("reasoning", "")).strip()
        llm_calls += 1

    except Exception as e:
        print(f"Supervisor fallback used: {e}")

        # If supervisor fails, run the complete workflow.
        selected_agents = AGENT_ORDER.copy()
        constraints = empty_constraints()
        reasoning = "Supervisor routing failed, so the full workflow was used."

    return {
        "guardrail_allowed": True,
        "guardrail_reason": reason,
        "selected_agents": selected_agents,
        "trip_constraints": constraints,
        "supervisor_reasoning": reasoning,
        "messages": [AIMessage(content="Travel workflow selected.")],
        "llm_calls": llm_calls,
    }


# Flight Agent
def flight_agent(state: TravelState):
    print("\nINSIDE FLIGHT AGENT\n")

    query = state["user_query"]

    try:
        airports = asyncio.run(
            aviation_mcp_call("list_airports")
        )

        airlines = asyncio.run(
            aviation_mcp_call("list_airlines")
        )

        prompt = f"""
You are an expert travel flight planner.

User request:
{query}

Airport information:
{airports}

Airline information:
{airlines}

Generate:

1. Likely departure airport
2. Likely arrival airport
3. Airlines serving the route
4. Typical flight duration
5. Estimated airfare range
6. Peak season pricing warning
7. Booking advice

Do not invent live prices.
Clearly mention when pricing is unavailable.
"""

        response = llm.invoke([
            SystemMessage(
                content="You are an expert flight planner."
            ),
            HumanMessage(content=prompt),
        ])

        flight_results = str(response.content)

    except Exception as e:
        print(f"Flight agent error: {e}")
        flight_results = f"Flight information unavailable: {e}"

    return {
        "flight_results": flight_results,
        "messages": [
            AIMessage(content="Flight information fetched.")
        ],
        "llm_calls": state.get("llm_calls", 0) + 1,
    }


# Hotel Agent
def hotel_agent(state: TravelState):
    print("\nINSIDE HOTEL AGENT\n")

    query = f"Best hotels for {state['user_query']}"

    try:
        hotel_results = asyncio.run(
            tavily_mcp_search(query)
        )
    except Exception as e:
        print(f"Hotel agent error: {e}")
        hotel_results = f"Hotel information unavailable: {e}"

    return {
        "hotel_results": hotel_results,
        "messages": [
            AIMessage(content="Hotel information fetched.")
        ],
        "llm_calls": state.get("llm_calls", 0) + 1,
    }


# Weather Agent
def weather_agent(state: TravelState):
    print("\nINSIDE WEATHER AGENT\n")

    try:
        city = extract_destination(
            state["user_query"]
        )

        weather_data = asyncio.run(
            weather_mcp_search(city)
        )

        forecast_data = asyncio.run(
            forecast_mcp_search(city)
        )

        weather_results = f"""
Current Weather:
{weather_data}

Forecast:
{forecast_data}
"""

    except Exception as e:
        print(f"Weather agent error: {e}")
        weather_results = f"Weather information unavailable: {e}"

    return {
        "weather_results": weather_results,
        "messages": [
            AIMessage(content="Weather information fetched.")
        ],
        "llm_calls": state.get("llm_calls", 0) + 1,
    }


# Budget Agent
def budget_agent(state: TravelState):
    print("\nINSIDE BUDGET AGENT\n")

    prompt = f"""
You are a travel budget analyst.

User request:
{state["user_query"]}

Trip constraints:
{state.get("trip_constraints", {})}

Flight information:
{state.get("flight_results", "")}

Hotel information:
{state.get("hotel_results", "")}

Estimate the trip cost.

Include:
- Flights
- Hotels
- Food
- Local transportation
- Sightseeing
- Miscellaneous expenses
- Total estimated cost
- Whether the user's budget is realistic

Use price ranges when exact prices are unavailable.
Do not present estimates as live prices.
"""

    try:
        response = llm.invoke([
            SystemMessage(
                content="You are a practical travel budget analyst."
            ),
            HumanMessage(content=prompt),
        ])

        budget_results = str(response.content)

    except Exception as e:
        print(f"Budget agent error: {e}")
        budget_results = f"Budget information unavailable: {e}"

    return {
        "budget_results": budget_results,
        "messages": [
            AIMessage(content="Budget information generated.")
        ],
        "llm_calls": state.get("llm_calls", 0) + 1,
    }


# Itinerary Agent
def itinerary_agent(state: TravelState):
    print("\nINSIDE ITINERARY AGENT\n")

    prompt = f"""
Create a complete travel itinerary.

User request:
{state["user_query"]}

Flight Results:
{state.get("flight_results", "")}

Hotel Results:
{state.get("hotel_results", "")}

Weather Results:
{state.get("weather_results", "")}

Budget Results:
{state.get("budget_results", "")}

Trip Constraints:
{state.get("trip_constraints", {})}

Make the itinerary practical, budget-aware and easy to follow.

Include:
- Trip summary
- Day-by-day activities
- Hotel suggestions
- Flight guidance
- Food suggestions
- Local transportation
- Weather considerations
- Estimated spending
- Total estimated budget

Do not invent live flight prices.
"""

    try:
        response = llm.invoke([
            SystemMessage(
                content="You are an expert travel itinerary planner."
            ),
            HumanMessage(content=prompt),
        ])

        itinerary = str(response.content)

    except Exception as e:
        print(f"Itinerary agent error: {e}")
        itinerary = f"Unable to create itinerary: {e}"

    return {
        "itinerary": itinerary,
        "messages": [
            AIMessage(content="Draft itinerary created.")
        ],
        "llm_calls": state.get("llm_calls", 0) + 1,
    }


# Human-in-the-Loop
def human_review_agent(state: TravelState):
    print("\nWAITING FOR HUMAN APPROVAL\n")

    approval_request = (
        "Please review the draft itinerary. "
        "Approve it if you are satisfied or provide "
        "feedback if you want changes."
    )

    review = interrupt({
        "type": "travel_plan_review",
        "message": approval_request,
        "draft": state.get("itinerary", ""),
    })

    return {
        "approved": bool(
            review.get("approved", False)
        ),
        "human_feedback": str(
            review.get("feedback", "")
        ).strip(),
        "approval_request": approval_request,
        "messages": [
            AIMessage(content="Human review completed.")
        ],
    }


# Final Response Agent
def final_agent(state: TravelState):
    print("\nINSIDE FINAL AGENT\n")

    prompt = f"""
Create the final travel plan.

User request:
{state["user_query"]}

Flights:
{state.get("flight_results", "")}

Hotels:
{state.get("hotel_results", "")}

Weather:
{state.get("weather_results", "")}

Budget:
{state.get("budget_results", "")}

Draft itinerary:
{state.get("itinerary", "")}

Human feedback:
{state.get("human_feedback", "")}

Format the final answer using:

1. Trip Summary
2. Flight Information
3. Hotel Suggestions
4. Weather Information
5. Day-by-Day Itinerary
6. Estimated Budget
7. Final Recommendations

Important:
- Be clear and practical.
- Keep the user's budget in mind.
- Include weather-based advice.
- Do not invent live flight prices.
- Mention when prices are estimates.
- Apply the human feedback when provided.
"""

    try:
        response = llm.invoke([
            SystemMessage(
                content="You are a professional AI travel assistant."
            ),
            HumanMessage(content=prompt),
        ])

        final_response = str(response.content)

    except Exception as e:
        print(f"Final agent error: {e}")
        final_response = f"Unable to generate final plan: {e}"

    return {
        "final_response": final_response,
        "messages": [
            AIMessage(content=final_response)
        ],
        "llm_calls": state.get("llm_calls", 0) + 1,
    }


# Decide which agent should run next
def route_after_supervisor(state: TravelState):
    if not state.get("guardrail_allowed", True):
        return END

    selected_agents = state.get(
        "selected_agents",
        []
    )

    if not selected_agents:
        return "itinerary_agent"

    return selected_agents[0]


def route_to_next_agent(state: TravelState):
    selected_agents = state.get(
        "selected_agents",
        []
    )

    completed = []

    if state.get("flight_results"):
        completed.append("flight_agent")

    if state.get("hotel_results"):
        completed.append("hotel_agent")

    if state.get("weather_results"):
        completed.append("weather_agent")

    if state.get("budget_results"):
        completed.append("budget_agent")

    if state.get("itinerary"):
        completed.append("itinerary_agent")

    for agent in selected_agents:
        if agent not in completed:
            return agent

    return END


def route_after_human_review(state: TravelState):
    if state.get("approved", False):
        return "final_agent"

    return "itinerary_agent"


# Build LangGraph
graph = StateGraph(TravelState)

graph.add_node(
    "supervisor_agent",
    supervisor_agent
)

graph.add_node(
    "flight_agent",
    flight_agent
)

graph.add_node(
    "hotel_agent",
    hotel_agent
)

graph.add_node(
    "weather_agent",
    weather_agent
)

graph.add_node(
    "budget_agent",
    budget_agent
)

graph.add_node(
    "itinerary_agent",
    itinerary_agent
)

graph.add_node(
    "human_review_agent",
    human_review_agent
)

graph.add_node(
    "final_agent",
    final_agent
)

graph.add_edge(
    START,
    "supervisor_agent"
)

graph.add_conditional_edges(
    "supervisor_agent",
    route_after_supervisor,
)

for agent in [
    "flight_agent",
    "hotel_agent",
    "weather_agent",
    "budget_agent",
]:
    graph.add_conditional_edges(
        agent,
        route_to_next_agent,
    )

graph.add_edge(
    "itinerary_agent",
    "human_review_agent"
)

graph.add_conditional_edges(
    "human_review_agent",
    route_after_human_review,
)

graph.add_edge(
    "final_agent",
    END
)


# PostgreSQL Checkpointer
DATABASE_URL = get_database_url()

_conn = psycopg.connect(
    DATABASE_URL,
    autocommit=True,
    row_factory=dict_row,
)

checkpointer = PostgresSaver(_conn)
checkpointer.setup()

travel_graph = graph.compile(
    checkpointer=checkpointer
)


# Run a new travel request
def run_travel_agent(
    user_input: str,
    thread_id: str | None = None,
):
    if not thread_id:
        thread_id = f"user_{uuid.uuid4().hex}"

    config = {
        "configurable": {
            "thread_id": thread_id
        }
    }

    result = travel_graph.invoke(
        {
            "messages": [
                HumanMessage(content=user_input)
            ],
            "user_query": user_input,

            "guardrail_allowed": True,
            "guardrail_reason": "",

            "selected_agents": [],
            "supervisor_reasoning": "",
            "trip_constraints": empty_constraints(),

            "flight_results": "",
            "hotel_results": "",
            "weather_results": "",
            "budget_results": "",
            "itinerary": "",

            "approval_request": "",
            "approved": False,
            "human_feedback": "",

            "final_response": "",
            "llm_calls": 0,
        },
        config=config,
    )

    final_answer = result.get(
        "final_response",
        ""
    )

    return {
        "thread_id": thread_id,
        "answer": final_answer,
        "itinerary": result.get("itinerary", ""),
        "flight_results": result.get("flight_results", ""),
        "hotel_results": result.get("hotel_results", ""),
        "weather_results": result.get("weather_results", ""),
        "budget_results": result.get("budget_results", ""),
        "selected_agents": result.get("selected_agents", []),
        "supervisor_reasoning": result.get(
            "supervisor_reasoning",
            ""
        ),
        "guardrail_allowed": result.get(
            "guardrail_allowed",
            True
        ),
        "guardrail_reason": result.get(
            "guardrail_reason",
            ""
        ),
        "requires_approval": not bool(final_answer),
        "approval_request": result.get(
            "approval_request",
            "Please review the draft itinerary."
        ),
        "llm_calls": result.get(
            "llm_calls",
            0
        ),
    }


# Resume the graph after human approval/revision
def resume_travel_agent(
    thread_id: str,
    approved: bool,
    feedback: str = "",
):
    config = {
        "configurable": {
            "thread_id": thread_id
        }
    }

    result = travel_graph.invoke(
        Command(
            resume={
                "approved": approved,
                "feedback": feedback,
            }
        ),
        config=config,
    )

    final_answer = result.get(
        "final_response",
        ""
    )

    return {
        "thread_id": thread_id,
        "answer": final_answer,
        "itinerary": result.get("itinerary", ""),
        "flight_results": result.get("flight_results", ""),
        "hotel_results": result.get("hotel_results", ""),
        "weather_results": result.get("weather_results", ""),
        "budget_results": result.get("budget_results", ""),
        "selected_agents": result.get("selected_agents", []),
        "supervisor_reasoning": result.get(
            "supervisor_reasoning",
            ""
        ),
        "guardrail_allowed": result.get(
            "guardrail_allowed",
            True
        ),
        "guardrail_reason": result.get(
            "guardrail_reason",
            ""
        ),
        "requires_approval": False,
        "approval_request": "",
        "llm_calls": result.get(
            "llm_calls",
            0
        ),
    }