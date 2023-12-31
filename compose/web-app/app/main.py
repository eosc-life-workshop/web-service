from typing import Union

from fastapi import FastAPI

import os

hostname = os.environ['HOST_NAME']

app = FastAPI(root_path="/p/"+hostname+"/80")


@app.get("/")
def read_root():
    return {"Hello": "World"}


@app.get("/items/{item_id}")
def read_item(item_id: int, q: Union[str, None] = None):
    return {"item_id": item_id, "q": q}