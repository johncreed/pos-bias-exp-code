#!/bin/bash

data_path=$1
pos_bias=$2
gpu=$3
mode=$4
ps='wops'

if [ -z "$1" ] || [ -z "$2" ] || [ -z "$3" ] || [ -z "$4" ] ; then
	echo "Plz input: data_path & pos_bias & gpu_idx & mode!!!!!"
	exit 0
fi

root=`pwd`

run_exp(){
	cdir=$1
	rdir=$2
	mode=$3
	model_name=$4
	cmd="cd ${cdir}"
	cmd="${cmd}; ./grid.sh ${gpu} ${mode} ${model_name} ${ps}" 
	cmd="${cmd}; ./do-test.sh ${gpu} ${mode} ${model_name} ${ps}"
	cmd="${cmd}; ./do-pred.sh ${gpu} ${mode} ${ps}"
	cmd="${cmd}; echo 'va_logloss va_auc' > ${mode}.record"
	cmd="${cmd}; python select_params.py logs ${mode} | rev | cut -d' ' -f1-2 | rev >> ${mode}.record" # va logloss, auc
	cmd="${cmd}; head -n10 test-score.${mode}/rnd*log >> ${mode}.record" # va logloss, auc
	cmd="${cmd}; cd ${rdir}"
	echo ${cmd}
}

set -e
exp_dir=`basename ${data_path}`

for mn in 'ffm'
do
	for i in 'det'
	do
		cdir=${exp_dir}/derive.${i}.${mn}.${ps}
		mkdir -p ${cdir}
		ln -sf ${root}/scripts/*.sh ${cdir}
		ln -sf ${root}/scripts/*.py ${cdir}
		ln -sf ${root}/${data_path}/derive/*gt*svm ${cdir}
		ln -sf ${root}/${data_path}/derive/item.svm ${cdir}
		ln -sf ${root}/${data_path}/derive/truth.svm ${cdir}
		for j in 'trva' 'tr' 'va'
		do
			ln -sf ${root}/${data_path}/derive/${i}_${j}.svm ${cdir}/${j}.svm
		done
		run_exp ${cdir} ${root} ${mode} ${mn} | xargs -0 -d '\n' -P 1 -I {} sh -c {} 
	done
done
