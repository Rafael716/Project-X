"""Project X — Entrypoint FastAPI para uvicorn main:app."""
from app import app, PORT

if __name__ == '__main__':
    import uvicorn
    print(f'Project X (FastAPI) escuchando en http://0.0.0.0:{PORT}')
    uvicorn.run('app:app', host='0.0.0.0', port=PORT, reload=True)
