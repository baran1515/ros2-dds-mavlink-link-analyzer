from glob import glob

from setuptools import setup

package_name = "comm_analyzer"

setup(
    name=package_name,
    version="1.0.0",
    packages=[package_name],
    data_files=[
        ("share/ament_index/resource_index/packages", ["resource/" + package_name]),
        ("share/" + package_name, ["package.xml"]),
        ("share/" + package_name + "/launch", glob("launch/*.launch.py")),
    ],
    install_requires=["setuptools"],
    zip_safe=True,
    maintainer="Baran Koc",
    description="DDS link measurement nodes",
    license="MIT",
    tests_require=["pytest"],
    entry_points={
        "console_scripts": [
            "probe_sender = comm_analyzer.probe_sender:main",
            "probe_echo = comm_analyzer.probe_echo:main",
            "telemetry_monitor = comm_analyzer.telemetry_monitor:main",
        ],
    },
)
