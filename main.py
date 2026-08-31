from TCT.server import mcp
from TCT import tracing

def main():
    """Entry point for tct-server script"""
    try:
        mcp.run()
    finally:
        # Spans are batched, so anything from the last few seconds is still
        # buffered at shutdown. No-op when tracing is off.
        tracing.flush()

if __name__ == "__main__":
    main()
