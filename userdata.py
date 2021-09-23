from math import isclose
from operator import truediv
import time
class UserData():
    userid = ""
    isLeave = False
    jointime = time.time()
    lasttime = time.time()
    filelist = []
    findcount = 0
    age = 0.0
    gender = ""
    def __init__(self,userid) -> None:
        self.userid = userid
    def find(self,filepath):
        if self.isLeave:
            self.isLeave = False
            self.findcount = 0
            self.jointime = time.time()
            self.filelist = []
        self.filelist.append(filepath)
            
        #被找到
        self.lasttime = time.time()
        self.findcount += 1

    def checkLeave(self):
        # 檢查確認是否離開
        if time.time() - self.lasttime > 3:
            self.isLeave = True
        return self.isLeave

    def ontime(self):
        # 計算停留時間
        return time.time() - self.jointime

    def getFileList(self):
        return self.filelist[-3:]
    
    def setGenderAge(self,gender,age):
        self.gender = gender
        self.age = age

    def getDict(self):
        return {"id":str(self.jointime),"age":str(int(self.age)),"sex":str(self.gender),"staytime":str(self.ontime())}
        # return {"id":str(self.jointime),"age":str(int(self.age)),"sex":"Female","staytime":str(self.ontime())}
        