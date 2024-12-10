import logging
from logging.handlers import RotatingFileHandler
from fastapi import FastAPI, HTTPException
from http import HTTPStatus
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime
import csv
import os
import hashlib
import zipfile
from fastapi.middleware.cors import CORSMiddleware

log_filename = "api_operations.log"
log_handler = RotatingFileHandler(log_filename, maxBytes=5 * 1024 * 1024, backupCount=3)
log_handler.setLevel(logging.INFO)
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
log_handler.setFormatter(formatter)

logger = logging.getLogger()
logger.addHandler(log_handler)
logger.setLevel(logging.INFO)

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],  
)

CSV_FILE = "database.csv"

class Pedido(BaseModel):
    id: int
    cliente_id: int
    valor_total: float = Field(..., gt=0, description="O valor total deve ser maior que 0")
    data: datetime
    quantidade_itens: int = Field(..., gt=0, description="A quantidade de itens deve ser maior que 0")

def ler_dados_csv():
    pedidos = []
    if os.path.exists(CSV_FILE):
        with open(CSV_FILE, mode="r", newline="", encoding="utf-8") as file:
            reader = csv.DictReader(file)
            for row in reader:
                pedidos.append(Pedido(**{**row, "data": datetime.fromisoformat(row["data"])}))
        logger.info(f"{len(pedidos)} pedidos carregados do arquivo CSV.")
    else:
        logger.warning(f"Arquivo CSV {CSV_FILE} não encontrado.")
    return pedidos

def escrever_dados_csv(pedidos):
    with open(CSV_FILE, mode="w", newline="", encoding="utf-8") as file:
        fieldnames = ["id", "cliente_id", "valor_total", "data", "quantidade_itens"]
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        for pedido in pedidos:
            writer.writerow({**pedido.dict(), "data": pedido.data.isoformat()})
    logger.info(f"{len(pedidos)} pedidos foram salvos no arquivo CSV.")

@app.get("/pedidos", response_model=List[Pedido])
def listar_pedidos():
    pedidos = ler_dados_csv()
    logger.info(f"Lista de pedidos requisitada, total de {len(pedidos)} pedidos.")
    return pedidos

@app.get("/pedidos/{pedido_id}", response_model=Pedido)
def obter_pedido(pedido_id: int):
    pedidos = ler_dados_csv()
    for pedido in pedidos:
        if pedido.id == pedido_id:
            logger.info(f"Pedido com ID {pedido_id} encontrado.")
            return pedido
    logger.error(f"Pedido com ID {pedido_id} não encontrado.")
    raise HTTPException(status_code=404, detail="Pedido não encontrado")

@app.post("/pedidos", response_model=Pedido, status_code=HTTPStatus.CREATED)
def criar_pedido(pedido: Pedido):
    pedidos = ler_dados_csv()
    if any(p.id == pedido.id for p in pedidos):
        logger.warning(f"Tentativa de criar pedido com ID duplicado: {pedido.id}")
        raise HTTPException(status_code=400, detail=f"O pedido com ID {pedido.id} já existe.")
    
    pedidos.append(pedido)
    escrever_dados_csv(pedidos)
    logger.info(f"Pedido com ID {pedido.id} criado com sucesso.")
    return pedido

@app.put("/pedidos/{pedido_id}", response_model=Pedido)
def atualizar_pedido(pedido_id: int, pedido_atualizado: Pedido):
    pedidos = ler_dados_csv()
    for i, pedido in enumerate(pedidos):
        if pedido.id == pedido_id:
            pedidos[i] = pedido_atualizado
            escrever_dados_csv(pedidos)
            logger.info(f"Pedido com ID {pedido_id} atualizado com sucesso.")
            return pedido_atualizado
    logger.error(f"Pedido com ID {pedido_id} não encontrado para atualização.")
    raise HTTPException(status_code=404, detail=f"Pedido com ID {pedido_id} não encontrado")

@app.delete("/pedidos/{pedido_id}", status_code=204)
def deletar_pedido(pedido_id: int):
    pedidos = ler_dados_csv()
    pedidos_filtrados = [pedido for pedido in pedidos if pedido.id != pedido_id]
    if len(pedidos) == len(pedidos_filtrados):
        logger.warning(f"Tentativa de deletar pedido inexistente: {pedido_id}")
        raise HTTPException(status_code=404, detail=f"Pedido com ID {pedido_id} não encontrado")
    
    escrever_dados_csv(pedidos_filtrados)
    logger.info(f"Pedido com ID {pedido_id} deletado com sucesso.")
    return {"detail": "Pedido deletado"}

@app.get("/pedidosquantidade", response_model=dict)
def obter_quantidade_pedidos():
    pedidos = ler_dados_csv()
    quantidade = len(pedidos)
    logger.info(f"Total de {quantidade} pedidos cadastrados.")
    return {"quantidade": quantidade}

@app.get("/pedidoshash", response_model=dict)
def obter_hash_csv():
    hash_sha256 = calcular_hash_sha256()
    logger.info(f"Hash SHA256 do arquivo CSV calculado com sucesso.")
    return {"hash_sha256": hash_sha256}

def calcular_hash_sha256():
    sha256_hash = hashlib.sha256()
    with open(CSV_FILE, "rb") as file:
        for byte_block in iter(lambda: file.read(4096), b""):
            sha256_hash.update(byte_block)
    return sha256_hash.hexdigest()

@app.get("/pedidoscompactar", response_class=FileResponse)
def compactar_csv():
    zip_filename = "database.zip"
    with zipfile.ZipFile(zip_filename, 'w', zipfile.ZIP_DEFLATED) as zipf:
        zipf.write(CSV_FILE, os.path.basename(CSV_FILE))
    logger.info(f"Arquivo CSV compactado com sucesso em {zip_filename}.")
    return FileResponse(zip_filename, media_type='application/zip', filename=zip_filename)

@app.get("/pedidosfiltrar", response_model=List[Pedido])
def filtrar_pedidos(
    cliente_id: Optional[int] = None,
    valor_minimo: Optional[float] = None,
    valor_maximo: Optional[float] = None,
    quantidade_minima: Optional[int] = None,
    quantidade_maxima: Optional[int] = None
):
    pedidos = ler_dados_csv()
    logger.info(f"Parâmetros recebidos: cliente_id={cliente_id}, valor_minimo={valor_minimo}, valor_maximo={valor_maximo}, quantidade_minima={quantidade_minima}, quantidade_maxima={quantidade_maxima}")

    if cliente_id is not None:
        pedidos = [pedido for pedido in pedidos if pedido.cliente_id == cliente_id]
    if valor_minimo is not None:
        pedidos = [pedido for pedido in pedidos if pedido.valor_total >= valor_minimo]
    if valor_maximo is not None:
        pedidos = [pedido for pedido in pedidos if pedido.valor_total <= valor_maximo]
    if quantidade_minima is not None:
        pedidos = [pedido for pedido in pedidos if pedido.quantidade_itens >= quantidade_minima]
    if quantidade_maxima is not None:
        pedidos = [pedido for pedido in pedidos if pedido.quantidade_itens <= quantidade_maxima]

    logger.info(f"{len(pedidos)} pedidos encontrados apos filtragem.")
    return pedidos