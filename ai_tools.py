import requests
import json
import uuid
SERVERIP = "http://192.168.50.100"
def GetMAC():
    r""" 針對單網卡 """
    addr = hex(uuid.getnode())[2:].upper()
    return '-'.join(addr[i:i+2] for i in range(0, len(addr), 2))

def updateData(data):
    # 上傳人員狀態至伺服器
    url = SERVERIP + ":8001/ai/aidata"
    payload={'uid':GetMAC(),
    'data': json.dumps(data)}
    headers = {}
    response = requests.request("POST", url, headers=headers, data=payload)

    print(response.text)


def getAgeGender(filelist):
    url = SERVERIP + ":5000/detects"
    payload = {'token': 'xcreensupermarket'}
    files = []
    count = 0
    for name in filelist:
        files.append(
            ('file'+str(len(files)), (name.split("/")[len(name.split("/"))-1], open(name, 'rb'), 'image/jpeg'))
        )
        count += 1
    headers = {}
    response = requests.request(
        "POST", url, headers=headers, data=payload, files=files)
    return json.loads(response.text)