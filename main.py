from fastapi import FastAPI

app = FastAPI()

@app.get("/")
async def root():
    return {"message": "Hello123 World"}


@app.get("/hello/{name}")
async def say_hello(name: str):
    return {"message": f"Hello321 {name}"}
