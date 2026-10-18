"""Start the UniSched website and API with one command."""
import argparse
import uvicorn

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='UniSched university timetable planner')
    parser.add_argument('--host', default='127.0.0.1')
    parser.add_argument('--port', default=8000, type=int)
    parser.add_argument('--reload', action='store_true', help='Reload after Python source changes')
    args = parser.parse_args()
    uvicorn.run('app.main:app', host=args.host, port=args.port, reload=args.reload)
