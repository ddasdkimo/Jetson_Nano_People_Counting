import threading
import time
import os
from userdata import UserData
from ai_tools import getAgeGender,updateData
import statistics
import shutil

import cv2
import numpy as np
import collections
import threading
import pycuda.driver as cuda

from utils.ssd import TrtSSD
from filterpy.kalman import KalmanFilter
from numba import jit
from sklearn.utils.linear_assignment_ import linear_assignment

import warnings

warnings.filterwarnings("ignore", category=DeprecationWarning)




s_img, s_boxes = None, None
inuser = {}
INPUT_HW = (300, 300)
MAIN_THREAD_TIMEOUT = 20.0  # 20 seconds
threadarrLock = threading.Lock()

class CheckPeople(threading.Thread):  # 確認人流狀況
    def run(self):
        isOn = []
        while(True):
            isOnTmp = []
            self.threadarrLock.acquire()
            for userdata in inuser:
                if inuser[userdata].checkLeave():
                    # print(userdata+" isLeave")
                    pass
                else:
                    # print(userdata+" isOn")
                    isOnTmp.append(inuser[userdata])
            self.threadarrLock.release()
            try:
                apidata = []
                for tmp in isOnTmp:
                    if tmp not in isOn:
                        # 新加入人員
                        print("新加入人員:"+str(tmp.jointime))
                        tmp.reset()
                        print("停留時間:"+str(tmp.ontime()))
                    else:
                        # 已存在
                        # if tmp.age == 0 and len(tmp.getFileList()) >= 3:
                        
                        # if len(tmp.getFileList()) >= 2 and (tmp.getFileListcount()<5 or tmp.age == 0):
                        #     data = getAgeGender(tmp.getFileList())
                        #     genderlist = []
                        #     agelist = []
                        #     for agegenderdata in data:
                        #         for agegenderdataitem in agegenderdata:
                        #             gender, age = agegenderdataitem["value"].split(",")
                        #             genderlist.append(gender)
                        #             agelist.append(float(age))
                        #     agemean = statistics.mean(agelist)
                        #     gender = max(genderlist,key=genderlist.count)
                        #     tmp.setGenderAge(gender,agemean)

                        # print("已存在人員:"+str(tmp.jointime))
                        # print("年齡:"+str(tmp.age))
                        # print("性別:"+str(tmp.gender))
                        print("ID:"+str(tmp.userid))
                        print("停留時間:"+str(tmp.ontime()))
                        # 後台只關注停留中的人
                        apidata.append(tmp.getDict())
                for tmp in isOn:
                    if tmp not in isOnTmp:
                        # 已離開
                        # print("已離開人員:"+str(tmp.jointime))
                        # print("年齡:"+str(tmp.age))
                        # print("性別:"+str(tmp.gender))
                        # print("停留時間:"+str(tmp.ontime()))
                        # print("刪除暫存資料:"+delpath)
                        delpath = "userfiles/"+tmp.userid
                        try:
                            shutil.rmtree(delpath)
                        except OSError as e:
                            print(e)
                        else:
                            print("done")
                            
                isOn = isOnTmp
                # 回傳資料至後台
                updateData(data=apidata)
                time.sleep(1)
            except Exception as e: 
                print("error!!!!!")
                time.sleep(3)

    def __init__(self,threadarrLock):
        threading.Thread.__init__(self)
        self.threadarrLock = threadarrLock
        



# SORT Multi object tracking

#iou
@jit
def iou(bb_test, bb_gt):
    xx1 = np.maximum(bb_test[0], bb_gt[0])
    yy1 = np.maximum(bb_test[1], bb_gt[1])
    xx2 = np.minimum(bb_test[2], bb_gt[2])
    yy2 = np.minimum(bb_test[3], bb_gt[3])
    w = np.maximum(0., xx2 - xx1)
    h = np.maximum(0., yy2 - yy1)
    wh = w * h
    o = wh / ((bb_test[2] - bb_test[0]) * (bb_test[3] - bb_test[1])
              + (bb_gt[2] - bb_gt[0]) * (bb_gt[3] - bb_gt[1]) - wh)
    return o

#[x1, y1, x2, y2] -> [u, v, s, r]
def convert_bbox_to_z(bbox):
    """
    Takes a bounding box in the form [x1,y1,x2,y2] and returns z in the form
      [u,v,s,r] where u,v is the centre of the box and s is the scale/area and r is
      the aspect ratio
    """
    w = bbox[2] - bbox[0]
    h = bbox[3] - bbox[1]
    x = bbox[0] + w / 2.
    y = bbox[1] + h / 2.
    s = w * h  # scale is just area
    r = w / float(h)
    return np.array([x, y, s, r]).reshape((4, 1))

#[u, v, s, r] -> [x1, y1, x2, y2]
def convert_x_to_bbox(x, score=None):
    """
    Takes a bounding box in the centre form [x,y,s,r] and returns it in the form
      [x1,y1,x2,y2] where x1,y1 is the top left and x2,y2 is the bottom right
    """
    w = np.sqrt(x[2] * x[3])
    h = x[2] / w
    if score == None:
        return np.array([x[0] - w / 2., x[1] - h / 2., x[0] + w / 2., x[1] + h / 2.]).reshape((1, 4))
    else:
        return np.array([x[0] - w / 2., x[1] - h / 2., x[0] + w / 2., x[1] + h / 2., score]).reshape((1, 5))

#
class KalmanBoxTracker(object):
    """
    This class represents the internel state of individual tracked objects observed as bbox.
    """
    count = 0

    def __init__(self, bbox):
        """
        Initialises a tracker using initial bounding box.
        """
        # define constant velocity model
        self.kf = KalmanFilter(dim_x=7, dim_z=4)
        self.kf.F = np.array(
            [[1, 0, 0, 0, 1, 0, 0], [0, 1, 0, 0, 0, 1, 0], [0, 0, 1, 0, 0, 0, 1], [0, 0, 0, 1, 0, 0, 0],
             [0, 0, 0, 0, 1, 0, 0], [0, 0, 0, 0, 0, 1, 0], [0, 0, 0, 0, 0, 0, 1]])
        self.kf.H = np.array(
            [[1, 0, 0, 0, 0, 0, 0], [0, 1, 0, 0, 0, 0, 0], [0, 0, 1, 0, 0, 0, 0], [0, 0, 0, 1, 0, 0, 0]])

        self.kf.R[2:, 2:] *= 10.
        self.kf.P[4:, 4:] *= 1000.  # give high uncertainty to the unobservable initial velocities
        self.kf.P *= 10.
        self.kf.Q[-1, -1] *= 0.01
        self.kf.Q[4:, 4:] *= 0.01

        self.kf.x[:4] = convert_bbox_to_z(bbox)
        self.time_since_update = 0
        self.id = KalmanBoxTracker.count
        KalmanBoxTracker.count += 1
        self.history = []
        self.hits = 0
        self.hit_streak = 0
        self.age = 0

    def update(self, bbox):
        """
        Updates the state vector with observed bbox.
        """
        self.time_since_update = 0
        self.history = []
        self.hits += 1
        self.hit_streak += 1
        self.kf.update(convert_bbox_to_z(bbox))

    def predict(self):
        """
        Advances the state vector and returns the predicted bounding box estimate.
        """
        if (self.kf.x[6] + self.kf.x[2]) <= 0:
            self.kf.x[6] *= 0.0
        self.kf.predict()
        self.age += 1
        if self.time_since_update > 0:
            self.hit_streak = 0
        self.time_since_update += 1
        self.history.append(convert_x_to_bbox(self.kf.x))
        return self.history[-1]

    def get_state(self):
        """
        Returns the current bounding box estimate.
        """
        return convert_x_to_bbox(self.kf.x)


def associate_detections_to_trackers(detections, trackers, iou_threshold=0.3):
    """
    Assigns detections to tracked object (both represented as bounding boxes)

    Returns 3 lists of matches, unmatched_detections and unmatched_trackers
    """
    if len(trackers) == 0:
        return np.empty((0, 2), dtype=int), np.arange(len(detections)), np.empty((0, 5), dtype=int)
    iou_matrix = np.zeros((len(detections), len(trackers)), dtype=np.float32)

    for d, det in enumerate(detections):
        for t, trk in enumerate(trackers):
            iou_matrix[d, t] = iou(det, trk)

    #Hungarian Algorithm
    matched_indices = linear_assignment(-iou_matrix)

    unmatched_detections = []
    for d, det in enumerate(detections):
        if d not in matched_indices[:, 0]:
            unmatched_detections.append(d)
    unmatched_trackers = []
    for t, trk in enumerate(trackers):
        if t not in matched_indices[:, 1]:
            unmatched_trackers.append(t)

    # filter out matched with low IOU
    matches = []
    for m in matched_indices:
        if iou_matrix[m[0], m[1]] < iou_threshold:
            unmatched_detections.append(m[0])
            unmatched_trackers.append(m[1])
        else:
            matches.append(m.reshape(1, 2))
    if len(matches) == 0:
        matches = np.empty((0, 2), dtype=int)
    else:
        matches = np.concatenate(matches, axis=0)

    return matches, np.array(unmatched_detections), np.array(unmatched_trackers)

#TensorRT Detection
class TrtThread(threading.Thread):
    def __init__(self, condition, cam, model, conf_th):
        """__init__

        # Arguments
            condition: the condition variable used to notify main
                       thread about new frame and detection result
            cam: the camera object for reading input image frames
            model: a string, specifying the TRT SSD model
            conf_th: confidence threshold for detection
        """
        threading.Thread.__init__(self)
        self.condition = condition
        self.cam = cam
        self.model = model
        self.conf_th = conf_th
        self.cuda_ctx = None  # to be created when run
        self.trt_ssd = None   # to be created when run
        self.running = False

    def run(self):
        global s_img, s_boxes, s_row_img

        print('TrtThread: loading the TRT SSD engine...')
        self.cuda_ctx = cuda.Device(0).make_context()  # GPU 0
        self.trt_ssd = TrtSSD(self.model, INPUT_HW)
        print('TrtThread: start running...')
        self.running = True
        while self.running:
            ret, imgtmp = self.cam.read()
            # imgtmp = cv2.imread("test.png")
            if imgtmp is None:
                break
            img = cv2.resize(imgtmp, (300, 300))
            boxes, confs, clss = self.trt_ssd.detect(img, self.conf_th)
            with self.condition:
                s_img, s_boxes, s_row_img = img, boxes, imgtmp
                self.condition.notify()
        del self.trt_ssd
        self.cuda_ctx.pop()
        del self.cuda_ctx
        print('TrtThread: stopped...')

    def stop(self):
        self.running = False
        self.join()


def get_frame(condition):
    frame = 0
    max_age = 15
    
    trackers = []
    
    global s_img, s_boxes, s_row_img, inuser
    
    print("frame number ", frame)
    frame += 1
    idstp = collections.defaultdict(list)
    # idcnt = []
    # incnt, outcnt = 0, 0
    
    while True:
        with condition:
            if condition.wait(timeout=MAIN_THREAD_TIMEOUT):
                row_img,img, boxes = s_row_img,s_img, s_boxes
            # else:
            #     raise SystemExit('ERROR: timeout waiting for img from child')
        row_h = s_row_img.shape[0]
        row_w = s_row_img.shape[1]
        img_h = s_img.shape[0]
        img_w = s_img.shape[1]
        boxes = np.array(boxes)
        H, W = s_row_img.shape[:2]

        trks = np.zeros((len(trackers), 5))
        to_del = []

        for t, trk in enumerate(trks):
            pos = trackers[t].predict()[0]
            trk[:] = [pos[0], pos[1], pos[2], pos[3], 0]
            if np.any(np.isnan(pos)):
                to_del.append(t)
        trks = np.ma.compress_rows(np.ma.masked_invalid(trks))
        for t in reversed(to_del):
            trackers.pop(t)
        
        matched, unmatched_dets, unmatched_trks = associate_detections_to_trackers(boxes, trks)
        
        # update matched trackers with assigned detections
        # print("++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++")
        for t, trk in enumerate(trackers):
            # print("id:"+str(trk.id)+"\tage:"+str(trk.age)+"\thits:"+str(trk.hits)+"\ttime_since_update:"+str(trk.time_since_update))
            if t not in unmatched_trks:
                d = matched[np.where(matched[:, 1] == t)[0], 0]
                trk.update(boxes[d, :][0])
                xmin, ymin, xmax, ymax = boxes[d, :][0]
                xmin = int(xmin * (row_w/img_w))
                xmax = int(xmax * (row_w/img_w))
                ymin = int(ymin * (row_h/img_h))
                ymax = int(ymax * (row_h/img_h))
                filepath = "userfiles/"+str(trk.id)+"/"+str(time.time())+".jpg"
                if not os.path.isdir("userfiles/"):
                    os.mkdir("userfiles/")
                if not os.path.isdir("userfiles/"+str(trk.id)):
                    os.mkdir("userfiles/"+str(trk.id))
                cv2.imwrite(filepath,row_img[ymin:ymax,xmin:xmax])
                inuser[str(trk.id)].find(filepath)
                cv2.rectangle(row_img, (xmin, ymin), (xmax, ymax), (0, 0, 255), 2)
                if str(trk.id) in inuser:
                    cv2.putText(row_img, "id: " + str(trk.id), (int(xmin) + 10, int(ymin) + 30), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 2)
                    cv2.putText(row_img, "gender:"+inuser[str(trk.id)].gender, (int(xmin) + 10, int(ymin) + 60), cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 0, 255), 2)
                    cv2.putText(row_img, "age:"+str(int(inuser[str(trk.id)].age)), (int(xmin) + 10, int(ymin) + 90), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 255), 2)
                    cv2.putText(row_img, "double check:"+str(int(inuser[str(trk.id)].doublecheck)), (int(xmin) + 10, int(ymin) + 120), cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
                    cv2.putText(row_img, "cont:"+str(int(inuser[str(trk.id)].getFileListcount())), (int(xmin) + 10, int(ymin) + 150), cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 0), 2)
                else:
                    cv2.putText(row_img, "id: " + str(trk.id), (int(xmin) - 10, int(ymin) - 10), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 2)
        #Total, IN, OUT count & Line
        cv2.putText(row_img, "Total: " + str(len(trackers)), (15, 25), cv2.FONT_HERSHEY_DUPLEX, 0.7, (255, 255, 255), 1)

        # create and initialise new trackers for unmatched detections
        for i in unmatched_dets:
            trk = KalmanBoxTracker(boxes[i, :])
            trackers.append(trk)

            trk.id = len(trackers)
            if not os.path.isdir("userfiles/"):
                    os.mkdir("userfiles/")
            if not os.path.isdir("userfiles/"+str(trk.id)):
                os.mkdir("userfiles/"+str(trk.id))
            userdata = UserData(str(trk.id))
            threadarrLock.acquire()
            inuser[str(trk.id)] = userdata
            threadarrLock.release()
            #new tracker id & u, v
            u, v = trk.kf.x[0], trk.kf.x[1]
            idstp[trk.id].append([u, v])

            if trk.time_since_update > max_age:
                trackers.pop(i)
        
        # cv2.imshow("dst",cv2.resize(row_img, (int(row_img.shape[1]/2), int(row_img.shape[0]/2))))
        # cv2.imwrite("./shm/"+str(time.time)+"tmp.jpg",row_img)
        cv2.imwrite("./shm/tmp.jpg",row_img)
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break


if __name__ == '__main__':
    checkPeople = CheckPeople(threadarrLock)
    checkPeople.start()
    model = 'ssd_mobilenet_v1_coco'
    cam = cv2.VideoCapture(0)
    # cam = cv2.VideoCapture("1.mp4")
    # cam = cv2.VideoCapture("2.mp4")
    # cam = cv2.VideoCapture("3.mp4")
    if not cam.isOpened():
        raise SystemExit('ERROR: failed to open camera!')

    cuda.init()  # init pycuda driver

    condition = threading.Condition()
    trt_thread = TrtThread(condition, cam, model, conf_th=0.5)
    trt_thread.start()  # start the child thread

    get_frame(condition)
    trt_thread.stop()   # stop the child thread

    cam.release()
    cv2.destroyAllWindows()