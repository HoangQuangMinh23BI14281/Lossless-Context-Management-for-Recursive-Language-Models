import io
import sys
import operator
from typing import Dict, Any, Optional
from RestrictedPython import compile_restricted_exec, safe_globals, limited_builtins, utility_builtins
from RestrictedPython.Guards import guarded_iter_unpack_sequence, safer_getattr
from RestrictedPython.PrintCollector import PrintCollector

from logger.repl_logger import setup_repl_logger

class REPLError(Exception):
    """Lỗi sinh ra trong quá trình chạy REPL."""
    pass

class REPLExecutor:
    """Môi trường Sandbox an toàn để chạy Python code sinh từ LLM."""

    def __init__(self, session_id: str = "default", max_output_chars: int = 2000):
        self.max_output_chars = max_output_chars
        self.logger = setup_repl_logger(session_id)

    def execute(self, code: str, env: Dict[str, Any]) -> str:
        """Thực thi mã Python trong môi trường hạn chế."""
        code = self._extract_code(code)

        if not code.strip():
            return "No code to execute"

        self.logger.debug(f"Executing Code:\n{code}")

        restricted_globals = self._build_globals(env)
        old_stdout = sys.stdout
        sys.stdout = captured_output = io.StringIO()

        try:
            byte_code = compile_restricted_exec(code)
            if byte_code.errors:
                raise REPLError(f"Compilation error: {', '.join(byte_code.errors)}")

            exec(byte_code.code, restricted_globals, env)

            output = captured_output.getvalue()

            # Lấy output từ print
            if '_print' in env and hasattr(env['_print'], '__call__'):
                print_collector = env['_print']
                if hasattr(print_collector, 'txt'):
                    output += ''.join(print_collector.txt)

            # Evaluate dòng cuối cùng nếu nó là expression
            lines = code.strip().split('\n')
            if lines:
                last_line = lines[-1].strip()
                if last_line and not any(kw in last_line for kw in ['=', 'import', 'def', 'class', 'if', 'for', 'while', 'with']):
                    try:
                        result = eval(last_line, restricted_globals, env)
                        if result is not None:
                            output += str(result) + '\n'
                    except:
                        pass

            if not output:
                return "Code executed successfully (no output)"

            if len(output) > self.max_output_chars:
                truncated = output[:self.max_output_chars]
                return f"{truncated}\n\n[Output truncated]"

            return output.strip()

        except Exception as e:
            self.logger.error(f"Execution Error: {e}")
            raise REPLError(f"Execution error: {str(e)}")

        finally:
            sys.stdout = old_stdout

    def _extract_code(self, text: str) -> str:
        if '```python' in text:
            start = text.find('```python') + len('```python')
            end = text.find('```', start)
            if end != -1:
                return text[start:end].strip()
        if '```' in text:
            start = text.find('```') + 3
            end = text.find('```', start)
            if end != -1:
                return text[start:end].strip()
        return text

    def _build_globals(self, env: Dict[str, Any]) -> Dict[str, Any]:
        restricted_globals = safe_globals.copy()
        restricted_globals.update(limited_builtins)
        restricted_globals.update(utility_builtins)

        restricted_globals['_iter_unpack_sequence_'] = guarded_iter_unpack_sequence
        restricted_globals['_getattr_'] = safer_getattr
        restricted_globals['_getitem_'] = lambda obj, index: obj[index]
        restricted_globals['_getiter_'] = iter
        restricted_globals['_print_'] = PrintCollector

        restricted_globals.update({
            'len': len, 'str': str, 'int': int, 'float': float, 'bool': bool, 'list': list, 
            'dict': dict, 'set': set, 'tuple': tuple, 'range': range, 'enumerate': enumerate, 
            'zip': zip, 'map': map, 'filter': filter, 'sum': sum, 'min': min, 'max': max, 
            'any': any, 'all': all, 'abs': abs, 'round': round, 'True': True, 'False': False, 'None': None
        })
        
        # Safe standard library
        import re, json, math
        restricted_globals.update({'re': re, 'json': json, 'math': math})
        return restricted_globals
