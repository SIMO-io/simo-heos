import sys, traceback, socket
import requests
from bs4 import BeautifulSoup


def discover_heos_devices(timeout=5):
    """
    Discovers HEOS devices using SSDP.
    """
    message = (
        "M-SEARCH * HTTP/1.1\r\n"
        "HOST: 239.255.255.250:1900\r\n"
        "MAN: \"ssdp:discover\"\r\n"
        "MX: 1\r\n"
        "ST: urn:schemas-denon-com:device:ACT-Denon:1\r\n"
        "\r\n"
    )

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 2)
    sock.settimeout(timeout)

    # Send discovery message
    sock.sendto(message.encode('utf-8'), ('239.255.255.250', 1900))

    devices = []
    try:
        while True:
            response, addr = sock.recvfrom(1024)
            devices.append(
                {'ip': addr[0], 'discovery_info': response.decode('utf-8')})
    except socket.timeout:
        pass  # Discovery timeout

    fully_discovered = []
    for device in devices:
        for line in device['discovery_info'].splitlines():
            if line.startswith('LOCATION'):
                http_start = line.find('http')
                if http_start < 1:
                    continue
                info_url = line[http_start:]
                try:
                    resp = requests.get(info_url, timeout=5)
                except:
                    continue
                if resp.status_code != 200:
                    continue
                try:
                    soup = BeautifulSoup(resp.content, 'lxml')
                except:
                    continue
                try:
                    device['uid'] = soup.findAll('udn')[0].text.strip().strip(
                        'uuid:').strip()
                    device['name'] = soup.findAll('friendlyname')[
                        0].text.strip()
                except:
                    print(traceback.format_exc(), file=sys.stderr)
                    continue
                fully_discovered.append(device)

    return fully_discovered

