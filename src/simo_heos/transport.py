import telnetlib, json, sys, traceback, time, threading
from queue import Queue
from urllib.parse import parse_qs


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
        self.buffer = Queue(maxsize=100)
        self.in_cmd = False
        self.authorized = False
        self.username = None
        self.password = None
        self.connect()
        self.cmd(f'heos://system/register_for_change_events?enable=on')


    def connect(self):
        self.connection = telnetlib.Telnet(self.ip, 1255, timeout=1)

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
        self.in_cmd = True
        response = None
        if not self.connection:
            try:
                self.connect()
            except:
                self.in_cmd = False
                return
        try:
            self.connection.write(f"{command}\r\n".encode())
            response = self.connection.read_until(b"\r\n", timeout).decode()
        except:
            pass
        self.connection = False
        self.in_cmd = False
        if not response:
            return
        try:
            data = json.loads(response)
        except:
            print(traceback.format_exc(), file=sys.stderr)
            return
        try:
            if data['heos']['command'] not in command:
                print(f"Wrong response: {response}", file=sys.stderr)
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
                    values[key] = float(val[0])
                except:
                    try:
                        values[key] = int(val[0])
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


    def __del__(self):
        """
        Ensures the connection is closed when the object is garbage collected.
        """
        self.connection.close()