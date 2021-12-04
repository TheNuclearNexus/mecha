__all__ = [
    "Codegen",
    "Accumulator",
    "ChildrenCollector",
    "CommandCollector",
    "RootCommandCollector",
    "visit_single",
    "visit_multiple",
    "visit_generic",
    "visit_body",
]


from contextlib import contextmanager
from dataclasses import dataclass, field, fields
from typing import (
    Any,
    Dict,
    Generator,
    Iterable,
    List,
    Literal,
    Optional,
    Tuple,
    Type,
    cast,
    overload,
)

from beet.core.utils import normalize_string, required_field

from mecha import AstChildren, AstCommand, AstNode, AstRoot, CommandSpec, Visitor, rule

from .ast import (
    AstAssignment,
    AstAssignmentTargetIdentifier,
    AstAttribute,
    AstCall,
    AstCommandInterpolation,
    AstDict,
    AstExpressionBinary,
    AstExpressionUnary,
    AstFunctionSignature,
    AstIdentifier,
    AstList,
    AstLookup,
    AstValue,
)


@dataclass
class Accumulator:
    """Utility for generating python code."""

    indentation: str = ""
    refs: List[Any] = field(default_factory=list)
    lines: List[str] = field(default_factory=list)
    counter: int = 0
    header: Dict[str, str] = field(default_factory=dict)

    def get_source(self) -> str:
        """Return the source code."""
        header = "".join(
            f"{variable} = {expression}\n"
            for expression, variable in self.header.items()
        )
        return header + "".join(self.lines)

    def helper(self, name: str, *args: Any) -> str:
        """Emit helper."""
        helper = f"_mecha_runtime.helpers[{name!r}]"

        if helper not in self.header:
            self.header[helper] = f"_mecha_helper_{normalize_string(name)}"

        return f"{self.header[helper]}({', '.join(map(str, args))})"

    def replace(self, node: str, **kwargs: str) -> str:
        """Emit replace helper."""
        return self.helper("replace", node, *(f"{k}={v}" for k, v in kwargs.items()))

    def missing(self) -> str:
        """Emit missing sentinel."""
        self.header["_mecha_runtime.helpers['missing']"] = f"_mecha_helper_missing"
        return f"_mecha_helper_missing"

    def children(self, nodes: Iterable[str]) -> str:
        """Emit children helper."""
        return self.helper("children", f"[{', '.join(nodes)}]")

    def make_ref(self, obj: Any) -> str:
        """Register ref."""
        index = len(self.refs)
        self.refs.append(obj)
        return f"_mecha_refs[{index}]"

    def make_ref_slice(self, objs: Iterable[Any]) -> str:
        """Register ref slice."""
        start = len(self.refs)
        self.refs.extend(objs)
        stop = len(self.refs)
        return f"_mecha_refs[{start}:{stop}]"

    def make_variable(self) -> str:
        """Create a unique variable name."""
        name = f"_mecha_var{self.counter}"
        self.counter += 1
        return name

    @contextmanager
    def block(self):
        """Wrap statements in an indented block."""
        previous_indentation = self.indentation
        self.indentation += "    "
        try:
            yield
        finally:
            self.indentation = previous_indentation

    def statement(self, code: str):
        """Emit statement."""
        self.lines.append(f"{self.indentation}{code}\n")


@dataclass
class ChildrenCollector:
    """Generic children collector."""

    acc: Accumulator
    start_index: int
    children: List[str] = field(default_factory=list)

    def add_static(self, *args: AstNode):
        self.children.extend(self.acc.make_ref(node) for node in args)

    def add_dynamic(self, *args: str):
        self.children.extend(args)

    def flush(self) -> str:
        return self.acc.children(self.children)


class CommandCollector(ChildrenCollector):
    """Collector for commands."""

    def add_static(self, *args: AstNode):
        if len(args) > 1:
            self.acc.statement(
                f"_mecha_runtime.commands.extend({self.acc.make_ref_slice(args)})"
            )
        elif args:
            self.acc.statement(
                f"_mecha_runtime.commands.append({self.acc.make_ref(args[0])})"
            )

    def add_dynamic(self, *args: str):
        for arg in args:
            self.acc.statement(f"_mecha_runtime.commands.append({arg})")


class RootCommandCollector(CommandCollector):
    """Collector for commands in a standalone root node."""

    def flush(self) -> str:
        commands = self.acc.make_variable()
        self.acc.lines[self.start_index :] = [
            f"    {line}" for line in self.acc.lines[self.start_index :]
        ]
        self.acc.lines.insert(
            self.start_index,
            f"{self.acc.indentation}with _mecha_runtime.scope() as {commands}:\n",
        )
        return self.acc.helper("children", commands)


@overload
def visit_single(
    node: AstNode,
) -> Generator[AstNode, Optional[List[str]], Optional[str]]:
    ...


@overload
def visit_single(
    node: AstNode,
    required: Literal[True],
) -> Generator[AstNode, Optional[List[str]], str]:
    ...


def visit_single(
    node: AstNode,
    required: bool = False,
) -> Generator[AstNode, Optional[List[str]], Optional[str]]:
    """Yield the node and make sure that it returns a single result."""
    result = yield node

    if result is None:
        if required:
            raise ValueError(
                f"Result required for {node.__class__.__name__} {result!r}."
            )
        return None

    if len(result) != 1:
        raise ValueError(
            f"Expected single result for {node.__class__.__name__} {result!r}."
        )

    return result[0]


def visit_multiple(
    children: AstChildren[AstNode],
    acc: Accumulator,
    children_collector: Type[ChildrenCollector] = ChildrenCollector,
) -> Generator[AstNode, Optional[List[str]], Optional[str]]:
    """Yield all the nodes and return a single result pointing to the new children."""
    current_count = 0
    collector = None
    index = len(acc.lines)

    for i, child in enumerate(children):
        result = yield child
        if result is None:
            continue
        if not collector:
            collector = children_collector(acc, index)

        lines = acc.lines[index:]
        del acc.lines[index:]
        collector.add_static(*children[current_count:i])
        acc.lines.extend(lines)
        collector.add_dynamic(*result)

        current_count = i + 1
        index = len(acc.lines)

    if collector:
        collector.add_static(*children[current_count:])
        return collector.flush()

    return None


def visit_generic(
    node: AstNode,
    acc: Accumulator,
    children_collector: Type[ChildrenCollector] = ChildrenCollector,
) -> Generator[AstNode, Optional[List[str]], Optional[str]]:
    """Recursively yield all the fields and return a result pointing to the updated node."""
    to_replace: Dict[str, str] = {}

    for f in fields(node):
        attribute = getattr(node, f.name)
        result = None

        if isinstance(attribute, AstChildren):
            attribute = cast(AstChildren[AstNode], attribute)
            result = yield from visit_multiple(attribute, acc, children_collector)

        elif isinstance(attribute, AstNode):
            result = yield from visit_single(attribute)

        if result is not None:
            to_replace[f.name] = result

    if not to_replace:
        return None

    return acc.replace(acc.make_ref(node), **to_replace)


def visit_body(
    node: AstRoot,
    acc: Accumulator,
) -> Generator[AstNode, Optional[List[str]], None]:
    """Emit each individual command in the current scope."""
    commands = cast(AstChildren[AstNode], node.commands)
    result = yield from visit_multiple(commands, acc, CommandCollector)
    if result is None:
        acc.statement(f"_mecha_runtime.commands.extend({acc.make_ref(node)}.commands)")


@dataclass
class Codegen(Visitor):
    """Code generator."""

    spec: CommandSpec = required_field()

    def __call__(self, node: AstRoot) -> Tuple[Optional[str], Optional[str], List[Any]]:  # type: ignore
        acc = Accumulator()
        result = self.invoke(node, acc)
        if result is None:
            return None, None, acc.refs
        elif len(result) != 1:
            raise ValueError(
                f"Expected single result for {node.__class__.__name__} {result!r}."
            )
        output = acc.make_variable()
        acc.statement(f"{output} = {result[0]}")
        return acc.get_source(), output, acc.refs

    @rule(AstNode)
    def fallback(
        self,
        node: AstNode,
        acc: Accumulator,
    ) -> Generator[AstNode, Optional[List[str]], Optional[List[str]]]:
        result = yield from visit_generic(node, acc)
        if result is None:
            return None
        return [result]

    @rule(AstRoot)
    def root(
        self,
        node: AstRoot,
        acc: Accumulator,
    ) -> Generator[AstNode, Optional[List[str]], Optional[List[str]]]:
        result = yield from visit_generic(node, acc, RootCommandCollector)
        if result is None:
            return None
        return [result]

    @rule(AstCommand, identifier="statement")
    def statement(
        self,
        node: AstCommand,
        acc: Accumulator,
    ) -> Generator[AstNode, Optional[List[str]], Optional[List[str]]]:
        value = yield from visit_single(node.arguments[0])
        if value is not None:
            acc.statement(value)
        return []

    @rule(AstCommand, identifier="def:function:body")
    def function(
        self,
        node: AstCommand,
        acc: Accumulator,
    ) -> Generator[AstNode, Optional[List[str]], Optional[List[str]]]:
        signature = cast(AstFunctionSignature, node.arguments[0])
        arguments: List[str] = [
            f"{arg.name}={acc.missing()}" if arg.default else arg.name
            for arg in signature.arguments
        ]

        acc.statement(f"def {signature.name}({', '.join(arguments)}):")

        with acc.block():
            for arg in signature.arguments:
                if arg.default:
                    acc.statement(f"if {arg.name} is {acc.missing()}:")
                    with acc.block():
                        value = yield from visit_single(arg.default, required=True)
                        acc.statement(f"{arg.name} = {value}")

            yield from visit_body(cast(AstRoot, node.arguments[1]), acc)

        return []

    @rule(AstCommand, identifier="return")
    @rule(AstCommand, identifier="return:value")
    def return_statement(
        self,
        node: AstCommand,
        acc: Accumulator,
    ) -> Generator[AstNode, Optional[List[str]], Optional[List[str]]]:
        statement = "return"
        if node.arguments:
            value = yield from visit_single(node.arguments[0], required=True)
            statement += f" {value}"
        acc.statement(statement)
        return []

    @rule(AstCommand, identifier="if:condition:body")
    def if_statement(
        self,
        node: AstCommand,
        acc: Accumulator,
    ) -> Generator[AstNode, Optional[List[str]], Optional[List[str]]]:
        condition = yield from visit_single(node.arguments[0], required=True)
        acc.statement(f"if {condition}:")
        with acc.block():
            yield from visit_body(cast(AstRoot, node.arguments[1]), acc)
        return []

    @rule(AstCommand, identifier="elif:condition:body")
    def elif_statement(
        self,
        node: AstCommand,
        acc: Accumulator,
    ) -> Generator[AstNode, Optional[List[str]], Optional[List[str]]]:
        condition = yield from visit_single(node.arguments[0], required=True)
        acc.statement(f"elif {condition}:")
        with acc.block():
            yield from visit_body(cast(AstRoot, node.arguments[1]), acc)
        return []

    @rule(AstCommand, identifier="else:body")
    def else_statement(
        self,
        node: AstCommand,
        acc: Accumulator,
    ) -> Generator[AstNode, Optional[List[str]], Optional[List[str]]]:
        acc.statement(f"else:")
        with acc.block():
            yield from visit_body(cast(AstRoot, node.arguments[0]), acc)
        return []

    @rule(AstCommand, identifier="while:condition:body")
    def while_statement(
        self,
        node: AstCommand,
        acc: Accumulator,
    ) -> Generator[AstNode, Optional[List[str]], Optional[List[str]]]:
        condition = yield from visit_single(node.arguments[0], required=True)
        acc.statement(f"while {condition}:")
        with acc.block():
            yield from visit_body(cast(AstRoot, node.arguments[1]), acc)
        return []

    @rule(AstCommand, identifier="for:target:in:iterable:body")
    def for_statement(
        self,
        node: AstCommand,
        acc: Accumulator,
    ) -> Generator[AstNode, Optional[List[str]], Optional[List[str]]]:
        target = yield from visit_single(node.arguments[0], required=True)
        iterable = yield from visit_single(node.arguments[1], required=True)
        acc.statement(f"for {target} in {iterable}:")
        with acc.block():
            yield from visit_body(cast(AstRoot, node.arguments[2]), acc)
        return []

    @rule(AstCommand, identifier="break")
    def break_statement(
        self,
        node: AstCommand,
        acc: Accumulator,
    ) -> Optional[List[str]]:
        acc.statement("break")
        return []

    @rule(AstCommand, identifier="continue")
    def continue_statement(
        self,
        node: AstCommand,
        acc: Accumulator,
    ) -> Optional[List[str]]:
        acc.statement("continue")
        return []

    @rule(AstCommandInterpolation)
    def command_interpolation(
        self,
        node: AstCommandInterpolation,
        acc: Accumulator,
    ) -> Generator[AstNode, Optional[List[str]], Optional[List[str]]]:
        tree = self.spec.tree.get(node.scope)
        if not tree:
            raise ValueError("Missing entry for command argument {scope!r}.")

        result = yield from visit_single(node.value, required=True)

        return [
            acc.helper(
                "set_location",
                acc.helper(f"convert:{tree.parser}", result, tree.properties or {}),
                acc.make_ref(node),
            )
        ]

    @rule(AstExpressionBinary)
    def binary(
        self,
        node: AstExpressionBinary,
        acc: Accumulator,
    ) -> Generator[AstNode, Optional[List[str]], Optional[List[str]]]:
        op = node.operator.replace("_", " ")
        left = yield from visit_single(node.left, required=True)
        right = yield from visit_single(node.right, required=True)
        return [f"({left} {op} {right})"]

    @rule(AstExpressionUnary)
    def unary(
        self,
        node: AstExpressionUnary,
        acc: Accumulator,
    ) -> Generator[AstNode, Optional[List[str]], Optional[List[str]]]:
        op = node.operator.replace("_", " ")
        value = yield from visit_single(node.value, required=True)
        return [f"({op} {value})"]

    @rule(AstValue)
    def value(self, node: AstValue, acc: Accumulator) -> Optional[List[str]]:
        return [repr(node.value)]

    @rule(AstIdentifier)
    def identifier(self, node: AstIdentifier, acc: Accumulator) -> Optional[List[str]]:
        return [node.value]

    @rule(AstList)
    def list(
        self,
        node: AstList,
        acc: Accumulator,
    ) -> Generator[AstNode, Optional[List[str]], Optional[List[str]]]:
        items: List[str] = []

        for item in node.items:
            value = yield from visit_single(item, required=True)
            items.append(value)

        return [f"[{', '.join(items)}]"]

    @rule(AstDict)
    def dict(
        self,
        node: AstDict,
        acc: Accumulator,
    ) -> Generator[AstNode, Optional[List[str]], Optional[List[str]]]:
        items: List[str] = []

        for item in node.items:
            key = yield from visit_single(item.key, required=True)
            value = yield from visit_single(item.value, required=True)
            items.append(f"{key}: {value}")

        return [f"{{{', '.join(items)}}}"]

    @rule(AstAttribute)
    def attribute(
        self,
        node: AstAttribute,
        acc: Accumulator,
    ) -> Generator[AstNode, Optional[List[str]], Optional[List[str]]]:
        value = yield from visit_single(node.value, required=True)
        return [acc.helper("get_attribute", value, repr(node.name))]

    @rule(AstLookup)
    def lookup(
        self,
        node: AstLookup,
        acc: Accumulator,
    ) -> Generator[AstNode, Optional[List[str]], Optional[List[str]]]:
        arguments: List[str] = []

        for arg in node.arguments:
            value = yield from visit_single(arg, required=True)
            arguments.append(value)

        value = yield from visit_single(node.value, required=True)

        return [f"{value}[{', '.join(arguments)}]"]

    @rule(AstCall)
    def call(
        self,
        node: AstCall,
        acc: Accumulator,
    ) -> Generator[AstNode, Optional[List[str]], Optional[List[str]]]:
        arguments: List[str] = []

        for arg in node.arguments:
            value = yield from visit_single(arg, required=True)
            arguments.append(value)

        value = yield from visit_single(node.value, required=True)

        return [f"{value}({', '.join(arguments)})"]

    @rule(AstAssignment)
    def assignment(
        self,
        node: AstAssignment,
        acc: Accumulator,
    ) -> Generator[AstNode, Optional[List[str]], Optional[List[str]]]:
        op = node.operator
        target = yield from visit_single(node.target, required=True)
        value = yield from visit_single(node.value, required=True)
        return [f"{target} {op} {value}"]

    @rule(AstAssignmentTargetIdentifier)
    def assignment_target_identifier(
        self,
        node: AstAssignmentTargetIdentifier,
        acc: Accumulator,
    ) -> Optional[List[str]]:
        return [node.value]
