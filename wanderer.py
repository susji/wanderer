import argparse
import csv
import os
from dataclasses import dataclass
from struct import unpack
from time import sleep

import pendulum
import serial
from pendulum.datetime import DateTime
from pendulum.duration import Duration

DEBUG = os.getenv("DEBUG", True)
PORT = os.getenv("PORT", "com1")


class ResponseError(Exception):
    pass


def debug(*args, **kwargs):
    if DEBUG:
        print(*args, **kwargs)


@dataclass
class Sample:
    time: DateTime
    temp: float
    vib: float


@dataclass
class Measurement:
    resolution_temperature: int
    resolution_vibration: int
    period_sampling: Duration
    period_storing: Duration
    time_start: DateTime
    time_current: DateTime
    samples: list[Sample]


class Wanderer:
    FMT_TIME = "YYMMDDHHmmss"

    def _write(self, buf: bytes | str):
        # Wanderer seems to be pretty pick when accepting writes. One character
        # at a time seemed most robust based on my tests.
        if isinstance(buf, str):
            buf = buf.encode()
        debug(f"write: [{len(buf)}] {buf}")
        for i in range(len(buf)):
            c = buf[i : i + 1]
            self.s.write(c)
        self.s.write(b"\r")

    def _read(self, n: int) -> bytes:
        r = self.s.read(n)
        if len(r) != n:
            raise ResponseError(f"wanted {n} bytes, got {len(r)}")
        return r

    def __enter__(self, port: str = PORT):
        s = serial.Serial()

        print(f"Connecting to port {port}...")

        s.port = port

        s.baudrate = 9600
        s.bytesize = serial.EIGHTBITS
        s.parity = serial.PARITY_NONE
        s.stopbits = serial.STOPBITS_ONE

        s.xonxoff = False
        s.rtscts = False
        s.dsrdtr = False
        s.timeout = 2

        s.rts = True  # Seems to use this one for extra power
        s.dtr = False  # Not connected in original straight cable

        s.open()

        self.s = s
        print("Reading NUL byte after init: ", self._read(1))

        return self

    def __exit__(self, type, value, traceback):
        self.s.close()

    @staticmethod
    def time_format(dt) -> str:
        return dt.format(Wanderer.FMT_TIME)

    @staticmethod
    def time_parse(raw: str | bytes):
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        return pendulum.from_format(raw, Wanderer.FMT_TIME)

    def _expect(self, what: bytes | str, extra: int = 0) -> bytes:
        if isinstance(what, str):
            what = what.encode(("utf-8"))
        debug(f"expect: {what}+{extra}")
        r = self._read(len(what) + extra)
        if r[: len(what)] != what:
            raise ResponseError(f"expecting {what}, got {r[:len(what)]}")
        return r

    @staticmethod
    def transform_raw_temp(raw: int) -> float:
        return raw / 2.0 - 30

    @staticmethod
    def transform_raw_vib(raw: int) -> float:
        # XXX This is a guess based on a few example around 1-3 G.
        return raw / 14.5

    def battery(self) -> int:
        self._write("BA")
        r = self._expect("BA", extra=4)
        val = int(r[3:5], base=16) - 100
        if val < 0:
            raise ResponseError(f"battery level less than zero: {val}")
        return val

    def measure(
        self,
        start,
        measure: Duration,
        period_sample: int,
        period_store: int,
        res_temp: int,
        res_vib: int,
    ):
        debug(
            f"measure: start={start}, period_sample={period_sample}, period_store={period_store}"
        )
        debug(f"         measure={measure}, res_temp={res_temp}, res_vib={res_vib}")
        # ??
        self._write("LN")
        self._expect("LN", extra=1)
        # ??
        self._write("EQ")
        self._expect("EQ")
        # Time Current
        self._write("TC " + Wanderer.time_format(pendulum.now()))
        self._expect("TC")
        # Time Start
        self._write("TS " + Wanderer.time_format(start))
        self._expect("TS")
        # Record Length
        hours = measure.hours if measure.hours > 0 else 1
        self._write(f"TL {hours:04}")
        self._expect("TL")
        # Sampling Period
        # manual says this specifies "how often sensors are read",
        # and can be between 1..10 sec.
        self._write(f"PS {period_sample:04}")
        self._expect("PS")
        # Store Period
        # manual says this specifies
        #
        # "how often Wanderer unit stores the sensor readings, or samples, to memory"
        #
        # It also says that the Wanderer has memory for 6540 samples.
        #
        self._write(f"PM {period_store:04}")
        self._expect("PM")
        # Vibration/Temperature Resolution
        #
        # manual says "Resolution" means the minimum relative deviation from previous
        # sample that we record a new value. Resolution of 1 seems to have a special
        # meaning of "no change is too small", but 2 means a minimum deviation of 2 %,
        # 3 means 3 % etc. Temperature and vibration resolutions have identical logic.
        #
        # In practice this means that larger values for resolution means we accept more
        # variance in values before recording a new entry.
        #
        self._write(f"RE {res_vib:02X}{res_temp:02X}")
        self._expect("RE")

    def read(self) -> Measurement:
        # If there's an ongoing measurement when we do a read, it will be stopped.
        # Wanderer will maintain the measurement values until a new one is programmed
        # or it loses power.
        debug("read")
        # ??
        self._write("EQ")
        self._expect("EQ")
        # ??
        self._write("AP")
        # ??
        sw = self._expect("SW ", extra=4 + 1)
        tc = Wanderer.time_parse(self._expect("TC ", extra=12 + 1)[3:-1])
        ts = Wanderer.time_parse(self._expect("TS ", extra=12 + 1)[3:-1])
        tl = pendulum.duration(hours=int(self._expect("TL ", extra=4 + 1)[3:-1]))
        ps = pendulum.duration(seconds=int(self._expect("PS ", extra=4 + 1)[3:-1]))
        pm = pendulum.duration(seconds=int(self._expect("PM ", extra=4 + 1)[3:-1]))
        re = self._expect("RE ", extra=4 + 1)[3:-1]
        re_vib = int(re[0:2], base=16)
        re_temp = int(re[2:4], base=16)
        # Maybe "How many values in each sample?"
        vs = self._expect("VS ", extra=2 + 1)
        # Sample Number, that is, amount of samples
        sn = self._expect("SN ", extra=4 + 1)

        debug(f"read: Time Current:           {tc}")
        debug(f"read: Time Start:             {ts}")
        debug(f"read: Time Length:            {tl}")
        debug(f"read: Sampling Period:        {ps}")
        debug(f"read: Store Period:           {pm}")
        debug(f"read: Vibration resolution:   {re_vib}")
        debug(f"read: Temperature resolution: {re_temp}")

        s = int(vs[3 : 3 + 2])
        n = int(sn[3 : 3 + 4])
        debug(f"read: vs={s} ({vs})")
        debug(f"read: sn={n} ({sn})")

        samples = []
        temps = []
        vibs = []
        if n >= 1:
            raw_samples = self._read(5 * n + 1)[:-1]
            for i in range(0, len(raw_samples), 5):
                slice = raw_samples[i : i + 5]
                # XXX Time shift is probably more third byte by itself.
                one, two, three, raw_temp, raw_vib = unpack("<BBBBB", slice)
                temp = Wanderer.transform_raw_temp(raw_temp)
                vib = Wanderer.transform_raw_vib(raw_vib)
                temps.append(temp)
                vibs.append(vib)
                print(f"{one:04} {two:04} {three:04} {temp:04} {vib:04}")
                samples.append(
                    Sample(
                        time=tc + pendulum.duration(minutes=three),
                        temp=temp,
                        vib=vib,
                    )
                )
            print(f"vib_max={max(vibs)}, temp_min={min(temps)}, temp_max={max(temps)}")
        return Measurement(
            resolution_temperature=re_temp,
            resolution_vibration=re_vib,
            period_sampling=ps,
            period_storing=pm,
            time_start=ts,
            time_current=tc,
            samples=samples,
        )


if __name__ == "__main__":
    p = argparse.ArgumentParser(formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    p.add_argument("--read", action="store_true", help="Read current measurement")
    p.add_argument("--measure", action="store_true", help="Program a new measurment")
    p.add_argument(
        "--res-temp",
        type=int,
        default=1,
        help="Temperature resolution [deg]",
    )
    p.add_argument("--res-vib", type=int, default=1, help="Vibration resolution [G]")
    p.add_argument("--period-sample", type=int, default=1, help="Sampling period [s]")
    p.add_argument(
        "--period-store", type=int, default=1, help="Memory store period [s]"
    )
    p.add_argument("--measure-secs", type=int, default=10, help="Time to measure [s]")
    p.add_argument(
        "--output-csv",
        type=str,
        help="When reading, store measurement data as CSV to this filepath",
    )
    args = p.parse_args()

    mt = pendulum.duration(seconds=args.measure)

    with Wanderer() as k:
        sleep(0.5)
        print(f"Battery level: {k.battery()} %")
        print(f"Battery level: {k.battery()} %")

        if args.measure:
            print("Programming a new measurement...")
            k.measure(
                pendulum.now(),
                mt,
                args.period_sample,
                args.period_store,
                args.res_temp,
                args.res_vib,
            )

        if args.read:
            print("Reading measurement...")
            m = k.read()
            print(f"Got {len(m.samples)} samples starting from {m.time_start}.")

            if len(m.samples) > 0 and args.output_csv:
                print(f"Writing samples to CSV file: {args.output_csv}")
                with open(args.output_csv, "w", newline="") as f:
                    fieldnames = ["timestamp", "temperature", "vibration"]
                    sw = csv.DictWriter(
                        f, quoting=csv.QUOTE_MINIMAL, fieldnames=fieldnames
                    )
                    sw.writeheader()
                    for sample in m.samples:
                        sw.writerow(
                            {
                                "timestamp": sample.time.to_iso8601_string(),
                                "temperature": sample.temp,
                                "vibration": sample.vib,
                            }
                        )

        # It's beneficial to try reading battery level even if the information isn't
        # interesting because it tells us that we're correctly parsing the serial stream
        # from our Wanderer.
        print(f"Battery level: {k.battery()} %")
