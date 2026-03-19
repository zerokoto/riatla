import websocket, json
ws = websocket.create_connection('ws://localhost:8765')
ws.send(json.dumps({"accion": "emocion_happy"}))
ws.close()
print("Comando enviado OK")
