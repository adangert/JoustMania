import common
import subprocess
from piaudio import Audio, InitAudio
import time
import shlex

if __name__ == "__main__":
    InitAudio()
    check_for_update('ivy')

def run_command(command):
    process = subprocess.Popen(shlex.split(command), stdout=subprocess.PIPE)
    outout = ""
    while True:
        
        output = process.stdout.readline().decode("utf-8") 
        if (output == "b''" or output == '') and process.poll() is not None:
            break
        if output:
            outout += output
            print(output.strip())
    rc = process.poll()
    return outout

def big_update(voice):
    Audio('audio/Menu/vox/' + voice + '/update_started.wav').start_effect_and_wait()
    current_hash = run_command("sudo runuser -l pi -c 'cd /home/pi/JoustMania/;git rev-parse HEAD'").strip()
    run_command("sudo runuser -l pi -c 'cd /home/pi/JoustMania/;git checkout master'")
    run_command("sudo runuser -l pi -c 'cd /home/pi/JoustMania/;git pull'")
    run_command("sudo /home/pi/JoustMania/setup.sh")
    #it failed if it got this far
    time.sleep(3)
    run_command("sudo runuser -l pi -c 'cd /home/pi/JoustMania/;git checkout {}'".format(current_hash))
    Audio('audio/Menu/vox/' + voice + '/joustmania_failed.wav').start_effect_and_wait()
    
def tester():
    current_hash = run_command("sudo runuser -l pi -c 'git rev-parse HEAD'").strip()
    print(current_hash)

def check_for_update(voice):
    process = run_command("sudo runuser -l pi -c 'cd /home/pi/JoustMania/;pwd'")
    process = run_command("sudo runuser -l pi -c 'cd /home/pi/JoustMania/;git fetch'")
    diff_files = run_command("sudo runuser -l pi -c 'cd /home/pi/JoustMania/;git diff origin/master --name-only'").split()
    print(diff_files)


    if('setup.sh' in diff_files):
        Audio('audio/Menu/vox/' + voice + '/large_update.wav').start_effect_and_wait()
        return True

    elif (len(diff_files) >= 1):
        print("doing small pull")
        pull = run_command("sudo runuser -l pi -c 'cd /home/pi/JoustMania/;git pull'")
        Audio('audio/Menu/vox/' + voice + '/joustmania_updated.wav').start_effect_and_wait()
        return False


    

