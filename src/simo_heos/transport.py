import telnetlib, json, sys, traceback, time, threading
from queue import Queue
from urllib.parse import parse_qs


class HEOSDeviceTransporter:

    def __init__(self, ip, uid):
        self.ip = ip
        self.uid = uid
        self.connection = telnetlib.Telnet(ip, 1255)
        self.buffer = Queue(maxsize=100)
        self.in_cmd = False
        self.authorized = False
        self.username = None
        self.password = None
        self.cmd(f'heos://system/register_for_change_events?enable=on')


    def receive(self):
        if self.in_cmd:
            return
        result = self.connection.read_very_eager()
        if not result:
            return
        for item in result.split(b"\r\n"):
            self.buffer.put(item.decode())


    def cmd(self, command, timeout=5):
        # clear responses that might not be caught on previous calls
        self.receive()
        self.in_cmd = True
        response = None
        try:
            self.connection.write(f"{command}\r\n".encode())
            response = self.connection.read_until(b"\r\n", timeout).decode()
        except:
            pass
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

        try:
            values = parse_qs(data['heos']['message'])
            for key, val in values.items():
                values[key] = val[0]
                try:
                    values[key] = float(values[key])
                except:
                    try:
                        values[key] = int(values[key])
                    except:
                        pass
        except:
            values = {}


        return {
            'status': data['heos']['result'],
            'msg': data['heos']['message'],
            'values': values,
            'payload': data.get('payload')
        }


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