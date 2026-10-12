# Nmap

Network scanner for host discovery and port scanning.

## Full port scan

```bash
# scan all ports
nmap -p- <target_ip>
```

## Service detection

Run version detection only on the ports that are open.

```bash
# -sV probes service versions, -sC runs the default scripts
nmap -sV -sC -p 22,80 <target_ip>
```
