from flask import Flask, render_template, Response, request
import cv2
import serial
import threading
import time
import json
import argparse

app = Flask(__name__)
camera = cv2.VideoCapture(0)  # веб камера

camera.set(cv2.CAP_PROP_FRAME_WIDTH, 320)   # Определенные разрешения с некоторыми камерами могут не работать, поэтому для
camera.set(cv2.CAP_PROP_FRAME_HEIGHT, 240)  # уменьшения разрешения можно также использовать resize в методе getFramesGenerator

controlX, controlY = 0.0, 0.0  # глобальные переменные вектора движения робота. Диапазоны: [-1, 1]


def getFramesGenerator():
    """ Генератор фреймов для вывода в веб-страницу, тут же можно поиграть с openCV"""
    global controlX, controlY
    while True:
        # time.sleep(0.01)  # ограничение fps (если видео тупит, можно убрать)

        iSee = False  # флаг: был ли найден контур

        success, frame = camera.read()  # Получаем фрейм с камеры

        if success:
            frame = cv2.resize(frame, (180, 120), interpolation=cv2.INTER_AREA)  # уменьшаем разрешение кадров (если
            # видео тупит, можно уменьшить еще больше)
            height, width = frame.shape[0:2]  # получаем разрешение кадра

            hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)  # переводим кадр из RGB в HSV
            binary = cv2.inRange(hsv, (18, 60, 100), (32, 255, 255))  # пороговая обработка кадра (выделяем все желтое)
            #binary = cv2.inRange(hsv, (0, 0, 0), (255, 255, 35))  # пороговая обработка кадра (выделяем все черное)

            """
            # Чтобы выделить все красное необходимо произвести две пороговые обработки, т.к. тон красного цвета в hsv 
            # находится в начале и конце диапазона hue: [0; 180), а в openCV, хз почему, этот диапазон не закольцован.
            # поэтому выделяем красный цвет с одного и другого конца, а потом просто складываем обе битовые маски вместе

            bin1 = cv2.inRange(hsv, (0, 60, 70), (10, 255, 255)) # красный цвет с одного конца
            bin2 = cv2.inRange(hsv, (160, 60, 70), (179, 255, 255)) # красный цвет с другого конца
            binary = bin1 + bin2  # складываем битовые маски
            """

            contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL,
                                           cv2.CHAIN_APPROX_NONE)  # получаем контуры выделенных областей

            if len(contours) != 0:  # если найден хоть один контур
                maxc = max(contours, key=cv2.contourArea)  # находим наибольший контур
                moments = cv2.moments(maxc)  # получаем моменты этого контура
                """
                # moments["m00"] - нулевой момент соответствует площади контура в пикселях,
                # поэтому, если в битовой маске присутствуют шумы, можно вместо
                # if moments["m00"] != 0:  # использовать
                
                if moments["m00"] > 20: # тогда контуры с площадью меньше 20 пикселей не будут учитываться 
                """
                if moments["m00"] > 20:  # контуры с площадью меньше 20 пикселей не будут учитываться
                    cx = int(moments["m10"] / moments["m00"])  # находим координаты центра контура по x
                    cy = int(moments["m01"] / moments["m00"])  # находим координаты центра контура по y

                    iSee = True  # устанавливаем флаг, что контур найден

                    controlX = 2 * (cx - width / 2) / width  # находим отклонение найденного объекта от центра кадра и
                    # нормализуем его (приводим к диапазону [-1; 1])

                    cv2.drawContours(frame, maxc, -1, (0, 255, 0), 1)  # рисуем контур
                    cv2.line(frame, (cx, 0), (cx, height), (0, 255, 0), 1)  # рисуем линию линию по x
                    cv2.line(frame, (0, cy), (width, cy), (0, 255, 0), 1)  # линия по y

            if iSee:    # если был найден объект
                controlY = 0.5  # начинаем ехать вперед с 50% мощностью 
            else:
                controlY = 0.0  # останавливаемся
                controlX = 0.0  # сбрасываем меру поворота

            miniBin = cv2.resize(binary, (int(binary.shape[1] / 4), int(binary.shape[0] / 4)),  # накладываем поверх
                                 interpolation=cv2.INTER_AREA)                                  # кадра маленькую
            miniBin = cv2.cvtColor(miniBin, cv2.COLOR_GRAY2BGR)                                 # битовую маску
            frame[-2 - miniBin.shape[0]:-2, 2:2 + miniBin.shape[1]] = miniBin             # для наглядности

            cv2.putText(frame, 'iSee: {};'.format(iSee), (width - 120, height - 5),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.25, (255, 0, 0), 1, cv2.LINE_AA)  # добавляем поверх кадра текст
            cv2.putText(frame, 'controlX: {:.2f}'.format(controlX), (width - 70, height - 5),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.25, (255, 0, 0), 1, cv2.LINE_AA)  # добавляем поверх кадра текст

            _, buffer = cv2.imencode('.jpg', frame)
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + buffer.tobytes() + b'\r\n')


@app.route('/video_feed')
def video_feed():
    """ Генерируем и отправляем изображения с камеры"""
    return Response(getFramesGenerator(), mimetype='multipart/x-mixed-replace; boundary=frame')


@app.route('/')
def index():
    """ Крутим html страницу """
    return render_template('index.html')


if __name__ == '__main__':
    # пакет, посылаемый на ардуинку
    msg = {
        "speedA": 0,  # в пакете посылается скорость на левый и правый борт тележки
        "speedB": 0  #
    }

    # параметры робота
    speedScale = 0.60  # определяет скорость в процентах (0.60 = 60%) от максимальной абсолютной
    maxAbsSpeed = 100  # максимальное абсолютное отправляемое значение скорости
    sendFreq = 10  # слать 10 пакетов в секунду

    parser = argparse.ArgumentParser()
    parser.add_argument('-p', '--port', type=int, default=5000, help="Running port")
    parser.add_argument("-i", "--ip", type=str, default='127.0.0.1', help="Ip address")
    parser.add_argument('-s', '--serial', type=str, default='/dev/ttyUSB0', help="Serial port")
    args = parser.parse_args()

    serialPort = serial.Serial(args.serial, 9600)   # открываем uart

    def sender():
        """ функция цикличной отправки пакетов по uart """
        global controlX, controlY
        while True:
            speedA = maxAbsSpeed * (controlY + controlX)    # преобразуем скорость робота,
            speedB = maxAbsSpeed * (controlY - controlX)    # в зависимости от положения джойстика

            speedA = max(-maxAbsSpeed, min(speedA, maxAbsSpeed))    # функция аналогичная constrain в arduino
            speedB = max(-maxAbsSpeed, min(speedB, maxAbsSpeed))    # функция аналогичная constrain в arduino

            msg["speedA"], msg["speedB"] = speedScale * speedA, speedScale * speedB     # урезаем скорость и упаковываем

            serialPort.write(json.dumps(msg, ensure_ascii=False).encode("utf8"))  # отправляем пакет в виде json файла
            time.sleep(1 / sendFreq)

    threading.Thread(target=sender, daemon=True).start()    # запускаем тред отправки пакетов по uart с демоном

    app.run(debug=False, host=args.ip, port=args.port)   # запускаем flask приложение
