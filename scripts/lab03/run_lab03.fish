#!/usr/bin/env fish
# Lab 3: runs sql/lab03 in the order of the kit README and saves every result to docs/lab03/output/.
# Needs the lab 2 core in PostgreSQL (docker compose up -d). Reads core only; creates objects in lab03_cf.
# Usage: fish scripts/lab03/run_lab03.fish

set -l root (path resolve (status dirname)/../..)
cd $root; or exit 1
set -l out docs/lab03/output
mkdir -p $out

function psql_file
    docker compose exec -T postgres psql -v ON_ERROR_STOP=1 -U cityflow_user -d cityflow_s08 < $argv[1]
end

function run_step --argument-names file
    echo "==> $file"
    psql_file sql/lab03/$file.sql > docs/lab03/output/$file.txt 2>&1
    or begin
        cat docs/lab03/output/$file.txt
        echo "ERROR in $file" >&2
        exit 1
    end
end

# one warm-up run (not counted) + three measured runs; the last plan is kept as the full plan
function bench --argument-names label
    set -l times
    for i in 0 1 2 3
        set -l plan (psql_file sql/lab03/06_bench_query.sql)
        or exit 1
        set -l t (string match -r 'Execution Time: ([0-9.]+) ms' -- $plan)[2]
        if test $i -eq 0
            echo "$label warm-up: $t ms (not counted)"
        else
            set -a times $t
            echo "$label run $i: $t ms"
        end
        if test $i -eq 3
            printf '%s\n' $plan > docs/lab03/plan_$label.txt
        end
    end
    set -l median (printf '%s\n' $times | sort -g | sed -n 2p)
    echo "$label median: $median ms"
end

docker compose exec -T postgres psql -U cityflow_user -d cityflow_s08 -At -c "SHOW server_version" > $out/server_version.txt; or exit 1

for f in 00_prepare 01_daily_report 02_check_daily 03_windows 04_check_windows 09_report_evidence
    run_step $f
end

# benchmark: copy without index -> measure -> index -> measure -> same result check
run_step 05_bench_prepare
begin
    bench before
    run_step 07_bench_index
    bench after
end > $out/bench_timings.txt; or exit 1
cat $out/bench_timings.txt
run_step 08_bench_check

grep -h "PASS\|FAIL" $out/02_check_daily.txt $out/04_check_windows.txt $out/08_bench_check.txt
