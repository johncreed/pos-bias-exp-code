# Init
#source activate py3.7
. ./init.sh

# Train file path
train='python ../../main.py'

# Fixed parameter
flag='train'
epoch=50
batch_size=1024

# Data set
ds='pos'
ds_part='tr'
ds_path='./'

# Log path
log_path="grid_logs"

# others
device="cuda:$1"
mn=$2

task(){
# Set up fixed parameter and train command
train_cmd="${train} --dataset_name ${ds} --dataset_part ${ds_part} --dataset_path ${ds_path} --flag ${flag} --model_name ${mn} --epoch ${epoch} --device ${device} --save_dir ${log_path} --batch_size ${batch_size}"

# Print out all parameter pair
for lr in 0.0001 0.001
do
    for wd in 1e-2 1e-4 1e-6 1e-8
    do
        for k in 64 16 32 
        do
            cmd=${train_cmd}
            cmd="${cmd} --learning_rate ${lr}"
            cmd="${cmd} --weight_decay ${wd}"
            cmd="${cmd} --embed_dim ${k}"
            echo "${cmd}"
        done
    done
done
}


# Check command
echo "Check command list (the command may not be runned!!)"
task
#wait


# Run
echo "Run"
task | xargs -0 -d '\n' -P 1 -I {} sh -c {}