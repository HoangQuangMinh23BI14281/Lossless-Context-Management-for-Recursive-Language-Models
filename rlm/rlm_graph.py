"""Graph tracking and visualization for recursive LLM calls (LCM Adaptation)."""

import uuid
from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List, Literal
import networkx as nx
from pyvis.network import Network

@dataclass
class LLMCall:
    call_id: str
    iteration: int
    prompt: str
    response: str
    model: str
    tokens_prompt: Optional[int] = None
    tokens_completion: Optional[int] = None
    latency_ms: Optional[float] = None
    timestamp: Optional[str] = None
    sequence_number: Optional[int] = None
    triggered_recursion: bool = False
    spawned_node_id: Optional[str] = None

    @property
    def total_tokens(self) -> Optional[int]:
        if self.tokens_prompt is not None and self.tokens_completion is not None:
            return self.tokens_prompt + self.tokens_completion
        return None

    def get_prompt_preview(self, max_len: int = 100) -> str:
        if len(self.prompt) <= max_len:
            return self.prompt
        return self.prompt[:max_len] + "..."

    def get_response_preview(self, max_len: int = 100) -> str:
        if len(self.response) <= max_len:
            return self.response
        return self.response[:max_len] + "..."

@dataclass
class REPLStep:
    iteration: int
    code: str
    output: str
    timestamp: Optional[str] = None

@dataclass
class GraphNode:
    node_id: str
    node_type: Literal['llm_call', 'code_execution', 'rlm_root'] = 'rlm_root'
    depth: int = 0
    parent_id: Optional[str] = None
    status: str = "pending"
    error: Optional[str] = None
    sequence_number: Optional[int] = None
    
    prompt: str = ""
    response: str = ""
    model: str = ""
    tokens_prompt: Optional[int] = None
    tokens_completion: Optional[int] = None
    latency_ms: Optional[float] = None
    
    code: str = ""
    output: str = ""
    iteration: int = 0
    
    query: str = ""
    context: str = ""
    answer: str = ""
    iterations: int = 0
    llm_calls: int = 0
    repl_steps: List[REPLStep] = field(default_factory=list)
    llm_calls_list: List[LLMCall] = field(default_factory=list)
    total_tokens: int = 0
    total_latency_ms: float = 0.0
    triggering_llm_call_id: Optional[str] = None
    
    @property
    def total_tokens_computed(self) -> Optional[int]:
        if self.node_type == 'llm_call' and self.tokens_prompt is not None and self.tokens_completion is not None:
            return self.tokens_prompt + self.tokens_completion
        return None
    
    def get_context_preview(self, max_len: int = 100) -> str:
        if len(self.context) <= max_len:
            return self.context
        return self.context[:max_len] + "..."
    
    def get_query_preview(self, max_len: int = 50) -> str:
        if len(self.query) <= max_len:
            return self.query
        return self.query[:max_len] + "..."
    
    def get_prompt_preview(self, max_len: int = 100) -> str:
        if len(self.prompt) <= max_len:
            return self.prompt
        return self.prompt[:max_len] + "..."
    
    def get_response_preview(self, max_len: int = 100) -> str:
        if len(self.response) <= max_len:
            return self.response
        return self.response[:max_len] + "..."
    
    def get_code_preview(self, max_len: int = 100) -> str:
        if len(self.code) <= max_len:
            return self.code
        return self.code[:max_len] + "..."
    
    def get_output_preview(self, max_len: int = 100) -> str:
        if len(self.output) <= max_len:
            return self.output
        return self.output[:max_len] + "..."

class RLMGraphTracker:
    def __init__(self):
        self.graph = nx.DiGraph()
        self.nodes: Dict[str, GraphNode] = {}
        self.root_node_id: Optional[str] = None
        self._llm_call_sequence_counter: int = 0
        self._current_call_ids: Dict[str, str] = {}
        self._operation_sequence_counter: int = 0
    
    def create_node(self, query: str = "", context: str = "", depth: int = 0, parent_id: Optional[str] = None) -> str:
        node_id = str(uuid.uuid4())
        node = GraphNode(node_id=node_id, query=query, context=context, depth=depth, parent_id=parent_id)
        self.nodes[node_id] = node
        self.graph.add_node(node_id, **self._node_to_dict(node))
        if self.root_node_id is None:
            self.root_node_id = node_id
        if parent_id is not None:
            self.graph.add_edge(parent_id, node_id)
        return node_id
    
    def create_llm_call_node(self, prompt: str, response: str, model: str, depth: int, parent_id: Optional[str] = None, iteration: int = 0, tokens_prompt: Optional[int] = None, tokens_completion: Optional[int] = None, latency_ms: Optional[float] = None, timestamp: Optional[str] = None) -> str:
        node_id = str(uuid.uuid4())
        self._operation_sequence_counter += 1
        self._llm_call_sequence_counter += 1
        
        node = GraphNode(
            node_id=node_id, node_type='llm_call', depth=depth, parent_id=parent_id,
            prompt=prompt, response=response, model=model, iteration=iteration,
            tokens_prompt=tokens_prompt, tokens_completion=tokens_completion, latency_ms=latency_ms,
            sequence_number=self._operation_sequence_counter, status='success'
        )
        
        self.nodes[node_id] = node
        self.graph.add_node(node_id, **self._node_to_dict(node))
        
        if self.root_node_id is None:
            self.root_node_id = node_id
        if parent_id is not None:
            self.graph.add_edge(parent_id, node_id)
            
        self._current_call_ids[node_id] = node_id
        return node_id
    
    def create_code_execution_node(self, code: str, output: str, iteration: int, depth: int, parent_id: Optional[str] = None, error: Optional[str] = None) -> str:
        node_id = str(uuid.uuid4())
        self._operation_sequence_counter += 1
        
        node = GraphNode(
            node_id=node_id, node_type='code_execution', depth=depth, parent_id=parent_id,
            code=code, output=output, iteration=iteration, error=error,
            sequence_number=self._operation_sequence_counter, status='error' if error else 'success'
        )
        
        self.nodes[node_id] = node
        self.graph.add_node(node_id, **self._node_to_dict(node))
        
        if parent_id is not None:
            self.graph.add_edge(parent_id, node_id)
        
        return node_id
    
    def update_node(self, node_id: str, answer: str = "", iterations: Optional[int] = None, llm_calls: Optional[int] = None, error: Optional[str] = None) -> None:
        if node_id not in self.nodes:
            return
        node = self.nodes[node_id]
        if answer:
            node.answer = answer
        if iterations is not None:
            node.iterations = iterations
        if llm_calls is not None:
            node.llm_calls = llm_calls
        if error is not None:
            node.error = error
            node.status = "error"
        elif answer:
            node.status = "success"
        self.graph.nodes[node_id].update(self._node_to_dict(node))
    
    def add_repl_step(self, node_id: str, iteration: int, code: str, output: str) -> None:
        if node_id not in self.nodes:
            return
        step = REPLStep(iteration=iteration, code=code, output=output)
        self.nodes[node_id].repl_steps.append(step)
        self.graph.nodes[node_id].update(self._node_to_dict(self.nodes[node_id]))

    def add_llm_call(self, node_id: str, call_id: str, iteration: int, prompt: str, response: str, model: str, tokens_prompt: Optional[int] = None, tokens_completion: Optional[int] = None, latency_ms: Optional[float] = None, timestamp: Optional[str] = None) -> None:
        if node_id not in self.nodes:
            return
        self._llm_call_sequence_counter += 1
        call = LLMCall(
            call_id=call_id, iteration=iteration, prompt=prompt, response=response, model=model,
            tokens_prompt=tokens_prompt, tokens_completion=tokens_completion, latency_ms=latency_ms,
            timestamp=timestamp, sequence_number=self._llm_call_sequence_counter
        )
        node = self.nodes[node_id]
        node.llm_calls_list.append(call)
        if call.total_tokens is not None:
            node.total_tokens += call.total_tokens
        if latency_ms is not None:
            node.total_latency_ms += latency_ms
        self._current_call_ids[node_id] = call_id
        self.graph.nodes[node_id].update(self._node_to_dict(node))
        return call

    def get_current_call_id(self, node_id: str) -> Optional[str]:
        return self._current_call_ids.get(node_id)

    def mark_call_triggered_recursion(self, node_id: str, call_id: str, spawned_node_id: str) -> None:
        if node_id not in self.nodes:
            return
        node = self.nodes[node_id]
        for call in node.llm_calls_list:
            if call.call_id == call_id:
                call.triggered_recursion = True
                call.spawned_node_id = spawned_node_id
                break
        self.graph.nodes[node_id].update(self._node_to_dict(node))

    def get_graph(self) -> nx.DiGraph:
        return self.graph
    
    def get_cumulative_stats(self, node_id: str) -> Dict[str, int]:
        """Tính toán số liệu đệ quy (descendants) của 1 node."""
        if node_id not in self.nodes:
            return {"descendant_count": 0, "cumulative_iterations": 0, "cumulative_llm_calls": 0}
        
        descendants = list(nx.descendants(self.graph, node_id))
        total_iters = self.nodes[node_id].iterations
        total_calls = self.nodes[node_id].llm_calls
        
        for d in descendants:
            total_iters += self.nodes[d].iterations
            total_calls += self.nodes[d].llm_calls
            
        return {
            "descendant_count": len(descendants),
            "cumulative_iterations": total_iters,
            "cumulative_llm_calls": total_calls
        }

    def save_html(self, output_path: str = "./rlm_graph.html", height: str = "800px", width: str = "100%") -> None:
        net = Network(height=height, width=width, directed=True, notebook=False)
        net.set_options("""
        {
          "physics": {
            "enabled": true,
            "hierarchicalRepulsion": {
              "centralGravity": 0.0,
              "springLength": 200,
              "springConstant": 0.01,
              "nodeDistance": 150,
              "damping": 0.09
            },
            "solver": "hierarchicalRepulsion"
          },
          "layout": {
            "hierarchical": {
              "enabled": true,
              "direction": "UD",
              "sortMethod": "directed",
              "levelSeparation": 150,
              "nodeSpacing": 200
            }
          },
          "nodes": {
            "shape": "box",
            "margin": 10,
            "widthConstraint": {
              "maximum": 300
            }
          },
          "edges": {
            "arrows": "to",
            "smooth": {
              "enabled": true,
              "type": "cubicBezier"
            }
          }
        }
        """)
        
        for node_id, node_data in self.nodes.items():
            if node_data.node_type == 'llm_call':
                label = f"LLM #{node_data.sequence_number or 0}"
                if node_data.depth > 0:
                    label += f" (D{node_data.depth})"
                if node_data.iteration > 0:
                    label += f" [i{node_data.iteration}]"
                prompt_preview = node_data.get_prompt_preview(50)
                if prompt_preview:
                    label += f"\\n{prompt_preview}"
                if node_data.total_tokens_computed:
                    label += f"\\n{node_data.total_tokens_computed} tokens"
            elif node_data.node_type == 'code_execution':
                label = f"Exec #{node_data.sequence_number or 0}"
                if node_data.depth > 0:
                    label += f" (D{node_data.depth})"
                if node_data.iteration > 0:
                    label += f" [i{node_data.iteration}]"
                code_preview = node_data.get_code_preview(50)
                if code_preview:
                    label += f"\\n{code_preview}"
            else:
                query_preview = node_data.get_query_preview(40)
                label = f"D{node_data.depth}"
                if node_data.iterations > 0:
                    label += f" ({node_data.iterations}i/{node_data.llm_calls}c)"
                cumulative = self.get_cumulative_stats(node_id)
                if cumulative['descendant_count'] > 0:
                    label += f"\\n+{cumulative['descendant_count']} descendants ({cumulative['cumulative_iterations']}i/{cumulative['cumulative_llm_calls']}c total)"
                if query_preview:
                    label += f"\\n{query_preview}"

            color = self._get_color_for_node(node_data)
            title = self._build_node_tooltip(node_data)
            net.add_node(node_id, label=label, title=title, color=color, level=node_data.depth)
        
        for edge in self.graph.edges():
            net.add_edge(edge[0], edge[1])
        
        net.save_graph(output_path)
    
    def _node_to_dict(self, node: GraphNode) -> Dict[str, Any]:
        return {
            'query': node.query,
            'context_preview': node.get_context_preview(),
            'answer': node.answer,
            'depth': node.depth,
            'iterations': node.iterations,
            'llm_calls': node.llm_calls,
            'llm_calls_list': node.llm_calls_list,
            'llm_calls_count': len(node.llm_calls_list),
            'total_tokens': node.total_tokens,
            'total_latency_ms': node.total_latency_ms,
            'repl_steps_count': len(node.repl_steps),
            'error': node.error,
            'status': node.status
        }
    
    def _get_color_for_node(self, node: GraphNode) -> str:
        if node.status == "error":
            return "#dc2626"
        if node.node_type == 'llm_call':
            llm_colors = ["#1e3a8a", "#3b82f6", "#60a5fa", "#93c5fd"]
            return llm_colors[min(node.depth, len(llm_colors) - 1)]
        if node.node_type == 'code_execution':
            exec_colors = ["#166534", "#22c55e", "#4ade80", "#86efac"]
            return exec_colors[min(node.depth, len(exec_colors) - 1)]
        if node.status == "success":
            return "#27ae60" if node.depth == 0 else "#2ecc71"
        depth_colors = ["#3498db", "#5dade2", "#f39c12", "#e67e22", "#9b59b6", "#1abc9c"]
        return depth_colors[min(node.depth, len(depth_colors) - 1)]
    
    def _build_node_tooltip(self, node: GraphNode) -> str:
        lines = [
            f"Node ID: {node.node_id[:8]}...",
            f"Type: {node.node_type}",
            f"Depth: {node.depth}",
            f"Status: {node.status}"
        ]
        if node.sequence_number:
            lines.append(f"Sequence: #{node.sequence_number}")
        if node.parent_id:
            lines.append(f"Parent: {node.parent_id[:8]}...")
        if node.node_type == 'llm_call':
            lines.extend(["", "LLM Call Details:", f"  Iteration: {node.iteration}"])
            if node.model: lines.append(f"  Model: {node.model}")
            if node.prompt: lines.extend(["", "Prompt:", node.get_prompt_preview(200)])
            if node.response: lines.extend(["", "Response:", node.get_response_preview(200)])
            if node.tokens_prompt and node.tokens_completion:
                lines.extend(["", "Tokens:", f"  Prompt: {node.tokens_prompt}", f"  Completion: {node.tokens_completion}", f"  Total: {node.total_tokens_computed}"])
            if node.latency_ms: lines.append(f"  Latency: {node.latency_ms:.1f}ms")
        elif node.node_type == 'code_execution':
            lines.extend(["", "Execution Details:", f"  Iteration: {node.iteration}"])
            if node.code: lines.extend(["", "Code:", node.get_code_preview(200)])
            if node.output: lines.extend(["", "Output:", node.get_output_preview(200)])
            if node.error: lines.extend(["", "Error:", node.error[:200] + "..." if len(node.error) > 200 else node.error])
        else:
            lines.extend(["", "RLM Details:"])
            if node.query: lines.extend(["  Query:", f"    {node.get_query_preview(100)}"])
            lines.extend([f"  Iterations: {node.iterations}", f"  LLM Calls: {node.llm_calls}"])
        return "\\n".join(lines).replace('"', "'")
