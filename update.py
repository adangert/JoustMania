import common
import subprocess
from piaudio import Audio, InitAudio
import time
import shlex
import os

if __name__ == "__main__":
    InitAudio()
    check_for_update('ivy')

def run_command(command):
    process = subprocess.Popen(shlex.split(command), stdout=subprocess.PIPE)
    outout = ""
    print("running command: {}".format(command))
    while True:
        
        output = process.stdout.readline().decode("utf-8") 
        if (output == "b''" or output == '') and process.poll() is not None:
            break
        if output:
            outout += output
            print(output.strip())
    rc = process.poll()
    print("returning: {}".format(outout))
    return outout

def big_update(voice):
    Audio('audio/Menu/vox/' + voice + '/update_started.wav').start_effect_and_wait()
    homename = run_command("logname").strip()
    current_hash = run_command("sudo runuser -l pi -c 'cd {};git rev-parse HEAD'".format(os.getcwd())).strip()
    run_command("sudo runuser -l {} -c 'cd {};git checkout master'".format(homename,os.getcwd()))
    run_command("sudo runuser -l {} -c 'cd {};git pull'".format(homename,os.getcwd()))
    run_command("sudo /home/{}/JoustMania/setup.sh".format(os.getlogin()))
    #it failed if it got this far
    time.sleep(3)
    run_command("sudo runuser -l {} -c 'cd {};git checkout {}'".format(homename,os.getcwd(),current_hash))
    Audio('audio/Menu/vox/' + voice + '/joustmania_failed.wav').start_effect_and_wait()
    
def tester():
    homename = run_command("logname").strip()
    current_hash = run_command("sudo runuser -l {} -c 'git rev-parse HEAD'".format(homename)).strip()
    print(current_hash)

def check_for_update(voice):
    print("checking out login@@@@@@@@@@@@@@@@@@@")
    print(os.getcwd())
    print(os.path.expanduser('~'))
    print(os.environ.get("USERNAME"))
    homename = run_command("logname").strip()
    #print(os.getlogin())
    process = run_command("sudo runuser -l {} -c 'cd {};pwd'".format(homename,os.getcwd()))
    process = run_command("sudo runuser -l {} -c 'cd {};git fetch'".format(homename,os.getcwd()))
    diff_files = run_command("sudo runuser -l {} -c 'cd {};git diff origin/master --name-only --cached'".format(homename,os.getcwd())).split()
    print(diff_files)


    if('setup.sh' in diff_files):
        Audio('audio/Menu/vox/' + voice + '/large_update.wav').start_effect_and_wait()
        return True

    elif (len(diff_files) >= 1):
        print("doing small pull")
        homename = run_command("logname").strip()
        pull = run_command("sudo runuser -l {} -c 'cd {};git pull'".format(homename,os.getcwd()))
        Audio('audio/Menu/vox/' + voice + '/joustmania_updated.wav').start_effect_and_wait()
        return False


    

