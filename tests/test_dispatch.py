from typing import Generator, List, Type

from mecha import (
    AstCommand,
    AstCoordinate,
    AstDustParticleParameters,
    AstMessage,
    AstMessageText,
    AstNode,
    AstNumber,
    AstParticle,
    AstResourceLocation,
    AstRoot,
    AstVector3,
    Mecha,
    Visitor,
    rule,
)


def test_visitor(mc: Mecha):
    ast = mc.parse("particle dust 1.0 0.5 0.5 1.0 7 7 7")

    numbers: List[AstNode] = []

    visitor = Visitor()
    visitor.add_rule(rule(AstNumber)(numbers.append))
    visitor.invoke(ast)

    assert numbers == [
        AstNumber(value=1),
        AstNumber(value=0.5),
        AstNumber(value=0.5),
        AstNumber(value=1),
    ]


def test_visitor_extend(mc: Mecha):
    ast = mc.parse("particle dust 1.0 0.5 7 1.0 7 7 7", type=AstCommand)

    nodes: List[Type[AstNode]] = []
    numbers: List[AstNumber] = []
    sevens: List[AstNumber] = []

    class Foo(Visitor):
        @rule
        def default(self, node: AstNode):
            nodes.append(type(node))
            yield from node

        @rule(AstNumber, value=7)
        def seven(self, node: AstNumber):
            sevens.append(node)

    visitor = Visitor()
    visitor.extend(rule(AstNumber)(numbers.append), Foo())
    visitor.invoke(ast)

    assert nodes == [
        AstCommand,
        AstParticle,
        AstResourceLocation,
        AstDustParticleParameters,
        AstVector3,
        AstCoordinate,
        AstCoordinate,
        AstCoordinate,
    ]

    assert numbers == [AstNumber(value=1), AstNumber(value=0.5), AstNumber(value=1)]
    assert sevens == [AstNumber(value=7)]


def test_visitor_result(mc: Mecha):
    ast = mc.parse("say hello\nsay world\n")

    class Foo(Visitor):
        @rule(AstRoot)
        def root(self, node: AstRoot) -> Generator[AstNode, str, List[str]]:
            commands: List[str] = []

            for command in node.commands:
                value = yield command
                commands.append(value)

            return commands

        @rule(AstCommand)
        def command(self, node: AstCommand) -> Generator[AstNode, str, str]:
            arguments: List[str] = []

            for argument in node.arguments:
                value = yield argument
                arguments.append(repr(value))

            return f"{node.identifier}(" + ", ".join(arguments) + ")"

        @rule(AstMessage)
        def message(self, node: AstMessage) -> str:
            return "".join(
                fragment.value
                for fragment in node.fragments
                if isinstance(fragment, AstMessageText)
            )

    assert Foo().invoke(ast) == ["say:message('hello')", "say:message('world')"]


def test_index(mc: Mecha):
    assert mc.steps.index(mc.lint) == 0
    assert mc.steps.index(mc.transform) == 1
    assert mc.steps.index(mc.optimize) == 2
    assert mc.steps.index(mc.check) == 3
