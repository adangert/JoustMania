import os
import shlex
import subprocess
import time

from services.audio.piaudio import Audio, InitAudio

if __name__ == "__main__":
    InitAudio()
    check_for_update("ivy")


def run_command(command):
    process = subprocess.Popen(shlex.split(command), stdout=subprocess.PIPE)
    outout = ""
    print(f"running command: {command}")
    while True:
        output = process.stdout.readline().decode("utf-8")
        if (output == "b''" or output == "") and process.poll() is not None:
            break
        if output:
            outout += output
            print(output.strip())
    rc = process.poll()
    print(f"returning: {outout}")
    return outout


def big_update(voice):
    Audio("audio/Menu/vox/" + voice + "/update_started.wav").start_effect_and_wait()
    homename = run_command("logname").strip()
    current_hash = run_command(
        f"sudo runuser -l pi -c 'cd {os.getcwd()};git rev-parse HEAD'"
    ).strip()
    run_command(f"sudo runuser -l {homename} -c 'cd {os.getcwd()};git checkout master'")
    run_command(f"sudo runuser -l {homename} -c 'cd {os.getcwd()};git pull'")
    run_command(f"sudo /home/{os.getlogin()}/JoustMania/setup.sh")
    # it failed if it got this far
    time.sleep(3)
    run_command(
        f"sudo runuser -l {homename} -c 'cd {os.getcwd()};git checkout {current_hash}'"
    )
    Audio("audio/Menu/vox/" + voice + "/joustmania_failed.wav").start_effect_and_wait()


def tester():
    homename = run_command("logname").strip()
    current_hash = run_command(
        f"sudo runuser -l {homename} -c 'git rev-parse HEAD'"
    ).strip()
    print(current_hash)


def check_for_update(voice):
    print("checking out login@@@@@@@@@@@@@@@@@@@")
    print(os.getcwd())
    print(os.path.expanduser("~"))
    print(os.environ.get("USERNAME"))
    homename = run_command("logname").strip()
    # print(os.getlogin())
    process = run_command(f"sudo runuser -l {homename} -c 'cd {os.getcwd()};pwd'")
    process = run_command(f"sudo runuser -l {homename} -c 'cd {os.getcwd()};git fetch'")
    diff_files = run_command(
        f"sudo runuser -l {homename} -c 'cd {os.getcwd()};git diff origin/master --name-only --cached'"
    ).split()
    print(diff_files)

    if "setup.sh" in diff_files:
        Audio("audio/Menu/vox/" + voice + "/large_update.wav").start_effect_and_wait()
        return True

    if len(diff_files) >= 1:
        print("doing small pull")
        homename = run_command("logname").strip()
        pull = run_command(f"sudo runuser -l {homename} -c 'cd {os.getcwd()};git pull'")
        Audio("audio/Menu/vox/" + voice + "/joustmania_updated.wav").start_effect_and_wait()
        return False
