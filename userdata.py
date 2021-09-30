from random import sample
from math import isclose
from operator import truediv
import statistics
import time
import os
from ai_tools import getAgeGender,updateData
import threading
class UserData():
    class updateAgeGender(threading.Thread):  # 確認人流狀況
        def run(self):
            while(self.myUserData.age==0 and self.myUserData.isLeave == False):
                print("id:"+self.myUserData.userid)
                try:
                    if self.myUserData.getFileListcount() >= 3:
                        filelist = self.myUserData.getFileList()
                        data = getAgeGender(filelist)
                        genderlist = []
                        agelist = []
                        for agegenderdata in data:
                            for agegenderdataitem in agegenderdata:
                                point = agegenderdataitem['point']
                                if point['ymin'] == 0 and point['xmin'] == 0:
                                    continue
                                gender, age = agegenderdataitem["value"].split(",")
                                genderlist.append(gender)
                                agelist.append(float(age))
                        if len(agelist) == 0:
                            self.myUserData.removefilelist(filelist)
                            print("id:"+self.myUserData.userid+"face no find")
                            time.sleep(0.2)
                            continue
                        agemean = statistics.mean(agelist)
                        gender = max(genderlist,key=genderlist.count)
                        self.myUserData.setGenderAge(gender,agemean)
                except:
                    print("age error")
                time.sleep(0.2)
            while(self.myUserData.doublecheck==False and self.myUserData.isLeave == False):
                print("double id:"+self.myUserData.userid)
                try:
                    # 10個以上 取出5個
                    doublefilelist = self.myUserData.getDoubleFileList()
                    if len(doublefilelist) >= 5:
                        data = getAgeGender(doublefilelist)
                        genderlist = []
                        agelist = []
                        for agegenderdata in data:
                            for agegenderdataitem in agegenderdata:
                                gender, age = agegenderdataitem["value"].split(",")
                                genderlist.append(gender)
                                agelist.append(float(age))
                        agemean = statistics.mean(agelist)
                        gender = max(genderlist,key=genderlist.count)
                        self.myUserData.setGenderAge(gender,agemean)
                        self.myUserData.doublecheck = True
                except:
                    print("age error")
                time.sleep(0.2)
        def __init__(self,myUserData):
            threading.Thread.__init__(self)
            self.myUserData = myUserData
            

    userid = ""
    isLeave = False
    jointime = time.time()
    lasttime = time.time()
    filelist = []
    findcount = 0
    doublecheck = False
    age = 0.0
    gender = ""
    def __init__(self,userid) -> None:
        self.userid = userid
        self.agegender = self.updateAgeGender(self)
        self.agegender.start()
        
    def find(self,filepath):
        if self.isLeave:
            self.isLeave = False
            self.findcount = 0
            self.jointime = time.time()
            self.filelist = []
            self.agegender = self.updateAgeGender(self)
            self.agegender.start()
        self.filelist.append(filepath)
            
        #被找到
        self.lasttime = time.time()
        self.findcount += 1
    def reset(self):
        self.jointime = time.time()
        self.lasttime = time.time()
        doublecheck = False
        self.filelist = []
        self.findcount = 0

    def checkLeave(self):
        # 檢查確認是否離開
        if time.time() - self.lasttime > 3:
            self.isLeave = True
        if self.isLeave:
            self.findcount = 0
            self.jointime = time.time()
            self.filelist = []
        return self.isLeave

    def ontime(self):
        # 計算停留時間
        return time.time() - self.jointime

    def getFileList(self):
        filearr = []
        # 檢查檔案是否存在
        for filepath in self.filelist:
            if os.path.isfile(filepath):
                filearr.append(filepath)
            # else:
            #     print("檔案不存在。")
        return filearr[-3:]
    def getDoubleFileList(self):
        filearr = []
        # 檢查檔案是否存在
        for filepath in self.filelist:
            if os.path.isfile(filepath):
                filearr.append(filepath)
            # else:
            #     print("檔案不存在。")
        if len(filearr) < 10:
            return []
        return sample(filearr,5)
    def getFileListcount(self):
        return len(self.filelist)
    def setGenderAge(self,gender,age):
        self.gender = gender
        self.age = age
    def removefilelist(self,filelist):
        for item in filelist:
            if item in self.filelist:
                self.filelist.remove(item)
                self.findcount -= 1
    def getDict(self):
        return {"id":str(self.jointime),"age":str(int(self.age)),"sex":str(self.gender),"staytime":str(self.ontime())}
        # return {"id":str(self.jointime),"age":str(int(self.age)),"sex":"Female","staytime":str(self.ontime())}
        