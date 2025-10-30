import telnetlib, json, sys, traceback, time, threading
from queue import Queue
from urllib.parse import parse_qs


class CommandLock(object):
    def __init__(self, transport):
        self.transport = transport

    def __enter__(self):
        self.transport.in_cmd = True

    def __exit__(self, *args):
        self.transport.in_cmd = False


class HEOSResponse:

    def __init__(self, status, msg, values, payload):
        self.status = status
        self.msg = msg
        self.values = values
        self.payload = payload

    def __str__(self):
        return f"HEOS RESPONSE STATUS: {self.status}\nMSG: {self.msg}" \
               f"\nVALUES: {self.values}\nPAYLOAD: {self.payload}"


class HEOSDeviceTransporter:

    def __init__(self, ip, uid):
        self.ip = ip
        self.uid = uid
        self.connection = None
        self.denon_connection = None
        self.buffer = Queue(maxsize=100)
        self.in_cmd = False
        self.authorized = False
        self.username = None
        self.password = None

        self.connect()
        self.denon_connect()

    def connect(self):
        self.connection = telnetlib.Telnet(self.ip, 1255, timeout=1)
        self.cmd(f'heos://system/register_for_change_events?enable=on')

    def denon_connect(self):
        try:
            self.denon_connection = telnetlib.Telnet(self.ip, 23)
        except:
            return

    def receive(self):
        if self.in_cmd:
            return
        if not self.connection:
            try:
                self.connect()
            except:
                return
        try:
            result = self.connection.read_very_eager()
        except EOFError:
            self.connection = None
            return
        if not result:
            return
        for item in result.split(b"\r\n"):
            try:
                self.buffer.put(json.loads(item.decode()))
            except:
                continue


    def cmd(self, command, timeout=5):
        # clear responses that might not be caught on previous calls
        self.receive()
        start = time.time()
        while self.in_cmd:
            time.sleep(0.1)
            if time.time() - start > 5:
                return
        with CommandLock(self):
            if not self.connection:
                try:
                    self.connect()
                except:
                    return
            try:
                self.connection.write(f"{command}\r\n".encode())
                while True:
                    response = self.connection.read_until(b"\r\n", timeout).decode()
                    try:
                        data = json.loads(response)
                    except:
                        #print(traceback.format_exc(), file=sys.stderr)
                        return
                    if data['heos']['message'].startswith('command under process'):
                        continue
                    if data['heos']['command'].startswith('event/'):
                        self.buffer.put(data)
                        continue
                    break
            except:
                self.connection = None
                return
            try:
                if data['heos']['command'] not in command:
                    print(f"Expected: {command} \nReceived: {response}\n", file=sys.stderr)
                    return
            except:
                print(traceback.format_exc(), file=sys.stderr)
                return

        return HEOSResponse(
            data['heos']['result'], data['heos']['message'],
            self.parse_values(data), data.get('payload')
        )

    def parse_values(self, data):
        try:
            values = parse_qs(data['heos']['message'])
            for key, val in values.items():
                try:
                    values[key] = int(val[0])
                except:
                    try:
                        values[key] = float(val[0])
                    except:
                        values[key] = val[0]
        except:
            values = {}
        return values


    def authorize(self, username, password):
        self.authorized = False
        self.username = None
        self.password = None
        self.cmd(f'heos://system/sign_in?un={username}&pw={password}')


    def denon_cmd(self, command, expect_response=False):
        if self.in_cmd:
            return

        if not self.denon_connection:
            self.denon_connect()
            if not self.denon_connection:
                return

        with CommandLock(self):

            # clear responses that might not be caught on previous calls
            try:
                self.denon_connection.read_very_eager()
                self.denon_connection.write(f"{command}".encode('utf-8'))
            except:
                self.denon_connection = None
                return

            start = time.time()
            if expect_response:
                if time.time() - start > 5:
                    return
                time.sleep(0.5)
                results = []
                try:
                    for item in self.denon_connection.read_very_eager().split(
                            b'\r'):
                        if not item:
                            continue
                        results.append(item.decode())
                except:
                    self.denon_connection = None
                if len(results):
                    return results
                return results



    def __del__(self):
        """
        Ensures the connection is closed when the object is garbage collected.
        """
        if self.connection:
            self.connection.close()
        if self.denon_connection:
            self.denon_connection.close()