from mcp.server.fastmcp import FastMCP

mcp = FastMCP("safe-example")


@mcp.tool(description="Add two integers without file, network, or system side effects")
def add(left: int, right: int) -> int:
    return left + right
