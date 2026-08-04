from langgraph.graph import StateGraph, START, END

from entities.claim_agent.state import ClaimAgentState
from entities.claim_agent.nodes.completeness import completeness_node
from entities.claim_agent.nodes.rules import rules_node
from entities.claim_agent.nodes.candidates import candidates_node
from entities.claim_agent.nodes.encoder import encoder_node
from entities.claim_agent.nodes.spanfilter import spanfilter_node
from entities.claim_agent.nodes.grouper import grouper_node
from entities.claim_agent.nodes.router import router_node


def build_claim_agent_graph():
    """Builds and compiles the Vitera claim-integrity pipeline.

        START -> completeness -> rules -> candidates -> encoder
              -> spanfilter -> grouper -> router -> END

    Everything left of `encoder` is deterministic. `encoder` is the only node
    that runs a model. Everything right of it exists to constrain what that
    model is allowed to say: spanfilter deletes what it cannot quote, grouper
    prices what survives, router decides what a human ever sees.
    """
    graph_builder = StateGraph(ClaimAgentState)

    graph_builder.add_node("completeness", completeness_node)
    graph_builder.add_node("rules", rules_node)
    graph_builder.add_node("candidates", candidates_node)
    graph_builder.add_node("encoder", encoder_node)
    graph_builder.add_node("spanfilter", spanfilter_node)
    graph_builder.add_node("grouper", grouper_node)
    graph_builder.add_node("router", router_node)

    graph_builder.add_edge(START, "completeness")
    graph_builder.add_edge("completeness", "rules")
    graph_builder.add_edge("rules", "candidates")
    graph_builder.add_edge("candidates", "encoder")
    graph_builder.add_edge("encoder", "spanfilter")
    graph_builder.add_edge("spanfilter", "grouper")
    graph_builder.add_edge("grouper", "router")
    graph_builder.add_edge("router", END)

    return graph_builder.compile()


# Module-level compiled claim agent graph
claim_agent_graph = build_claim_agent_graph()
