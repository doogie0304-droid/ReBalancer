import ast

for f in ["main.py", "notification.py", "config.py", "momentum_view_server.py"]:
    src = open(f, encoding="utf-8").read()
    try:
        ast.parse(src, filename=f)
        print(f"{f}: OK")
    except SyntaxError as e:
        print(f"{f}: SYNTAX ERROR - {e}")
