import argparse

import matplotlib.pyplot as plt
import pandas as pd
import pendulum


def do_plot(df):
    df["timestamp"] = df["timestamp"].map(lambda t: pendulum.parse(t))

    fig, ax_temp = plt.subplots()

    ax_temp.plot(
        df["timestamp"],
        df["temperature"],
        "-",
        marker="o",
        color="red",
        label="temperature",
    )

    ax_vib = ax_temp.twinx()
    ax_vib.plot(
        df["timestamp"],
        df["vibration"],
        "--",
        marker="x",
        color="blue",
        label="vibration",
    )

    ax_temp.set_xlabel("Time")
    ax_temp.set_ylabel("Temperature [deg C]")
    ax_vib.set_ylabel("Vibration [G]")

    for label in ax_temp.get_xticklabels():
        label.set_rotation(30)

    fig.legend()
    tsl = df["timestamp"].to_list()
    plt.title(f"{tsl[0]} - {tsl[-1]}")
    plt.show()


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument(
        "--input-csv", type=str, required=True, help="Wanderer CSV file to plot"
    )
    args = p.parse_args()
    do_plot(pd.read_csv(args.input_csv))
