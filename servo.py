try:
    from machine import PWM, Pin
    import utime

    USE_MOCK_SERVO = False
except ModuleNotFoundError:
    USE_MOCK_SERVO = True

import time
from math import fabs


class MockServo:
    def __init__(self):
        self.current_angle = 0.0

    def goto(self, angle: float):
        self.current_angle = angle
        time.sleep(1)


class PicoServo:
    def __init__(self, pin, min_duty_ns=500000, max_duty_ns=2500000, max_speed_ns=10000, min_angle=0.0,
                 max_angle=180.0):
        self.min_duty_ns = min_duty_ns
        self.max_duty_ns = max_duty_ns
        self.max_speed_ns = max_speed_ns

        self.min_angle = min_angle
        self.max_angle = max_angle
        self.mid_point = self.min_angle + (self.max_angle - self.min_angle) / 2.0

        duty_cycle_range_ns = max_duty_ns - min_duty_ns
        angle_range = max_angle - min_angle
        self.duty_ns_per_degree = duty_cycle_range_ns / angle_range

        self.pwm = PWM(pin)

        frequency_hz = 50
        self.pwm.freq(frequency_hz)
        self.transition_delay = 1.0 / frequency_hz

        self.current_angle = 0.0
        self._swipe_to_mid()

    def goto(self, angle: float):
        if angle < self.min_angle or angle > self.max_angle:
            raise RuntimeError(f'Bad angle: {angle}')

        self._travel_to_angle(angle)
        self.pwm.deinit()

    def _swipe_to_mid(self):
        # Swipe from min to max, and from max to min, to zero in the current position.
        # (the servo consumes too much current when trying to move to another point immediately, and doesn't move at
        # all)
        self.current_angle = self.min_angle
        self._travel_to_angle(self.max_angle)
        utime.sleep(0.1)
        self._travel_to_angle(self.min_angle)
        utime.sleep(0.1)
        self._travel_to_angle(self.mid_point)
        utime.sleep(0.1)
        self.pwm.deinit()

    def _degree_to_duty_ns(self, degree):
        return self.min_duty_ns + degree * self.duty_ns_per_degree

    def _duty_ns_to_degree(self, duty_ns):
        return self.min_angle + (duty_ns - self.min_duty_ns) / self.duty_ns_per_degree

    def _travel_to_angle(self, angle):
        start = int(self._degree_to_duty_ns(self.current_angle))
        stop = int(self._degree_to_duty_ns(angle))
        step = self.max_speed_ns if self.current_angle < angle else -self.max_speed_ns

        for i in range(start, stop, step):
            self.pwm.duty_ns(i)
            utime.sleep(self.transition_delay)
            self.current_angle = self._duty_ns_to_degree(i)


class Servo:
    PIN_NAME = "GPIO0"
    ON_ANGLE = 180.0
    OFF_ANGLE = 0.0

    def __init__(self):
        if USE_MOCK_SERVO:
            self.implementation = MockServo()
        else:
            self.implementation = PicoServo(Pin(Servo.PIN_NAME, Pin.OUT))

    def is_on(self):
        return fabs(self.implementation.current_angle - Servo.ON_ANGLE) < 1.0

    def is_off(self):
        return fabs(self.implementation.current_angle - Servo.OFF_ANGLE) < 1.0

    def turn_on(self):
        self.implementation.goto(Servo.ON_ANGLE)

    def turn_off(self):
        self.implementation.goto(Servo.OFF_ANGLE)
