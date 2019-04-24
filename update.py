import subprocess  
from piaudio import Audio, InitAudio
  
#almost working, need to get it to be a button push when it's a big update.  
  
if __name__ == "__main__":
    InitAudio()
    check_for_update() 

def run_command(command):
    process = subprocess.Popen(command.split(" "), stdout=subprocess.PIPE)
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
    
def big_update():
    Audio('audio/Menu/update_started.wav').start_effect_and_wait()
    run_command("git pull")
    run_command("sudo /home/pi/JoustMania/setup.sh")
    Audio('audio/Menu/joustmania_updated.wav').start_effect_and_wait()
    #audio, big update started
    #do big update
    #say big update completed
    
def check_for_update():
    process = run_command("git fetch")
    diff_files = run_command("git diff origin/master --name-only").split()
    print(diff_files)


    if('setup.sh' in diff_files):
        print('big updtae available')
        Audio('audio/Menu/large_update.wav').start_effect_and_wait()
        return True
        #audio cue here
        #run_command("sudo /home/pi/JoustMania/setup.sh")

    elif (len(diff_files) > 1):
        print("doing small pull")
        pull = run_command("git pull")
        Audio('audio/Menu/joustmania_updated.wav').start_effect_and_wait()
        return False

        #Audio('audio/Menu/tradeoff2.wav').start_effect_and_wait()
    
    
    

