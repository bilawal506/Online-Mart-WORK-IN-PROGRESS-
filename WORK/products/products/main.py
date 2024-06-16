# main.py

from contextlib import asynccontextmanager
from aiokafka import AIOKafkaProducer, AIOKafkaConsumer
from fastapi import FastAPI, Depends, HTTPException, status
from products import settings
from sqlmodel import SQLModel, create_engine, Field, Session, select
from typing import Any, AsyncGenerator, Optional, Annotated
import asyncio
from products import product_pb2
import logging
from .auth import TokenData, get_current_user  # Import the auth functions

logging.basicConfig(level=logging.DEBUG)

@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    print("LifeSpan Event..")
    asyncio.create_task(consume_messages('product', 'broker:19092'))
    yield

app = FastAPI(lifespan=lifespan)

connection_string = str(settings.DATABASE_URL).replace(
    "postgresql", "postgresql+psycopg"
)

class Product(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    price: int
    description: str
    category: str

engine = create_engine(
    connection_string, connect_args={}, pool_recycle=300
)

def create_db_and_tables():
    SQLModel.metadata.create_all(engine)

def get_session():
    with Session(engine) as session:
        yield session

async def get_kafka_producer():
    producer = AIOKafkaProducer(bootstrap_servers='broker:19092')
    await producer.start()
    try:
        print(f"Received message:")
        yield producer
    finally:
        await producer.stop()

async def consume_messages(topic, bootstrap_servers):
    consumer = AIOKafkaConsumer(
        topic,
        bootstrap_servers=bootstrap_servers,
        group_id="my-group",
        auto_offset_reset='earliest'
    )
    await consumer.start()
    try:
        async for message in consumer:
            print(f"Received message: {message.value} on topic {message.topic}")
            new_prd = product_pb2.Product()
            new_prd.ParseFromString(message.value)
            with Session(engine) as session:
                new_Product = Product(
                    id=new_prd.id,
                    name=new_prd.name,
                    price=new_prd.price,
                    description=new_prd.description,
                    category=new_prd.category
                )
                session.add(new_Product)
                session.commit()
                session.refresh(new_Product)
            print(f"Received message: {message.value.decode()} on topic {message.topic}")
    finally:
        await consumer.stop()

@app.get("/")
def hi():
    return {"Message": "I am the products microservice"}

@app.post("/add-product", response_model=Product)
async def create_product(product: Product, producer: Annotated[AIOKafkaProducer, Depends(get_kafka_producer)], current_user: TokenData = Depends(get_current_user)):
    product_message = product_pb2.Product()
    product_message.id = product.id
    product_message.name = product.name
    product_message.price = product.price
    product_message.description = product.description
    product_message.category = product.category

    product_message.operation = product_pb2.OperationType.CREATE

    await producer.send_and_wait("product", product_message.SerializeToString())
    return {"Product": "Created"}

@app.get("/products/{product_id}")
def get_product(product_id: int, session: Annotated[Session, Depends(get_session)], current_user: TokenData = Depends(get_current_user)):
    product = session.get(Product, product_id)
    return product

@app.get("/products/category/{category}")
def get_products_by_category(category: str, session: Annotated[Session, Depends(get_session)], current_user: TokenData = Depends(get_current_user)):
    products = session.exec(
        select(Product).where(Product.category == category)
    ).all()
    return products

@app.delete("/products/{product_id}")
def delete_product(product_id: int, session: Annotated[Session, Depends(get_session)], current_user: TokenData = Depends(get_current_user)):
    product = session.get(Product, product_id)
    session.delete(product)
    session.commit()
    return product

@app.get("/products")
def read_products(session: Annotated[Session, Depends(get_session)], current_user: TokenData = Depends(get_current_user)):
    products = session.exec(select(Product)).all()
    return products

@app.patch("/products/{product_id}")
def update_product(product_id: int, product: Product, session: Annotated[Session, Depends(get_session)], current_user: TokenData = Depends(get_current_user)):
    product_to_update = session.get(Product, product_id)
    if product_to_update is None:
        return {"message": "Product not found"}
    product_to_update.name = product.name
    product_to_update.price = product.price
    product_to_update.description = product.description
    product_to_update.category = product.category
    session.add(product_to_update)
    session.commit()
    session.refresh(product_to_update)
    return product_to_update

if __name__ == "__main__":
    create_db_and_tables()
