_start:
    li sp, 65532
    li t0, 4096
    li t1, 115
    sb t1, 0(t0)
    addi t0, t0, 1
    li t1, 117
    sb t1, 0(t0)
    addi t0, t0, 1
    li t1, 109
    sb t1, 0(t0)
    addi t0, t0, 1
    li t1, 32
    sb t1, 0(t0)
    addi t0, t0, 1
    li t1, 61
    sb t1, 0(t0)
    addi t0, t0, 1
    sb zero, 0(t0)
    jal ra, main
    ecall
main:
    addi sp, sp, -8
    sw ra, 4(sp)
    sw s0, 0(sp)
    mv s0, sp
    addi sp, sp, -2048
    li t0, 0
    sw t0, -4(s0)
    li t1, 1
    sw t1, -8(s0)
while_1:
    lw t2, -8(s0)
    li t3, 10
    slt t2, t3, t2
    xori t2, t2, 1
    beq t2, zero, wend_2
    lw t4, -4(s0)
    lw t5, -8(s0)
    add t4, t4, t5
    sw t4, -4(s0)
    lw t6, -8(s0)
    li s2, 1
    add t6, t6, s2
    sw t6, -8(s0)
    j while_1
wend_2:
    li s3, 4096
    mv a0, s3
    jal ra, forge_print_str
    li t0, 268435456
    li t1, 32
    sb t1, 0(t0)
    lw s4, -4(s0)
    mv a0, s4
    jal ra, forge_print_int
    li t0, 268435456
    li t1, 10
    sb t1, 0(t0)
    li s5, 0
    mv a0, s5
    ecall
    ecall
forge_print_str:
    addi sp, sp, -4
    sw ra, 0(sp)
forge_print_str_loop:
    lb t0, 0(a0)
    beq t0, zero, forge_print_str_done
    li t1, 268435456
    sb t0, 0(t1)
    addi a0, a0, 1
    j forge_print_str_loop
forge_print_str_done:
    lw ra, 0(sp)
    addi sp, sp, 4
    ret
forge_print_int:
    addi sp, sp, -4
    sw ra, 0(sp)
    li t0, -2147483648
    bne a0, t0, forge_print_int_sign
    li t0, 268435456
    li t1, 45
    sb t1, 0(t0)
    li a0, -2147483648
    j forge_print_int_push_u
forge_print_int_sign:
    blt a0, zero, forge_print_int_neg
    j forge_print_int_digits
forge_print_int_neg:
    li t0, 268435456
    li t1, 45
    sb t1, 0(t0)
    sub a0, zero, a0
forge_print_int_digits:
    beq a0, zero, forge_print_int_zero
    mv t3, sp
    li t2, 10
forge_print_int_push:
    beq a0, zero, forge_print_int_pop
    rem t0, a0, t2
    addi t0, t0, 48
    addi sp, sp, -4
    sw t0, 0(sp)
    div a0, a0, t2
    j forge_print_int_push
forge_print_int_push_u:
    mv t3, sp
    li t2, 10
forge_print_int_push_u_loop:
    beq a0, zero, forge_print_int_pop
    remu t0, a0, t2
    addi t0, t0, 48
    addi sp, sp, -4
    sw t0, 0(sp)
    divu a0, a0, t2
    j forge_print_int_push_u_loop
forge_print_int_pop:
    beq sp, t3, forge_print_int_done
    lw t0, 0(sp)
    addi sp, sp, 4
    li t1, 268435456
    sb t0, 0(t1)
    j forge_print_int_pop
forge_print_int_zero:
    li t0, 268435456
    li t1, 48
    sb t1, 0(t0)
forge_print_int_done:
    lw ra, 0(sp)
    addi sp, sp, 4
    ret
forge_strlen:
    li t0, 0
forge_strlen_loop:
    lb t1, 0(a0)
    beq t1, zero, forge_strlen_done
    addi a0, a0, 1
    addi t0, t0, 1
    j forge_strlen_loop
forge_strlen_done:
    mv a0, t0
    ret
forge_fsub:
    li t0, -2147483648
    xor a1, a1, t0
    j forge_fadd
forge_fadd:
    srli t0, a0, 31
    slli t0, t0, 31
    srli t1, a1, 31
    slli t1, t1, 31
    srli t2, a0, 23
    andi t2, t2, 255
    srli t3, a1, 23
    andi t3, t3, 255
    li t6, 8388607
    and t4, a0, t6
    and t5, a1, t6
    or t6, t2, t4
    bne t6, zero, fa_anotzero
    or t6, t3, t5
    beq t6, zero, fa_bothzero
    mv a0, a1
    ret
fa_bothzero:
    bne t0, t1, fa_bz_pos
    mv a0, t0
    ret
fa_bz_pos:
    li a0, 0
    ret
fa_anotzero:
    or t6, t3, t5
    bne t6, zero, fa_bnotzero
    ret
fa_bnotzero:
    li t6, 8388608
    or t4, t4, t6
    or t5, t5, t6
    li s5, 0
    li s6, 0
    li s7, 0
    li s11, 0
    bge t2, t3, fa_align_b
    sub s8, t3, t2
    mv s3, t3
    li s11, 1
    j fa_shift_a
fa_align_b:
    sub s8, t2, t3
    mv s3, t2
    li s11, 2
    j fa_shift_b
fa_shift_a:
    beq s8, zero, fa_addsub
    li t6, 25
    blt s8, t6, fa_shift_a_small
    sltu s7, zero, t4
    li t4, 0
    j fa_addsub
fa_shift_a_small:
    li t6, 1
    sll t6, t6, s8
    addi t6, t6, -1
    and s10, t4, t6
    addi s9, s8, -1
    srl s5, s10, s9
    andi s5, s5, 1
    li s6, 0
    li s9, 2
    blt s8, s9, fa_shift_a_rdone
    addi s9, s8, -2
    srl s6, s10, s9
    andi s6, s6, 1
fa_shift_a_rdone:
    li s7, 0
    li s9, 3
    blt s8, s9, fa_shift_a_sdone
    addi s9, s8, -2
    li t6, 1
    sll t6, t6, s9
    addi t6, t6, -1
    and t6, s10, t6
    sltu s7, zero, t6
fa_shift_a_sdone:
    srl t4, t4, s8
    j fa_addsub
fa_shift_b:
    beq s8, zero, fa_addsub
    li t6, 25
    blt s8, t6, fa_shift_b_small
    sltu s7, zero, t5
    li t5, 0
    j fa_addsub
fa_shift_b_small:
    li t6, 1
    sll t6, t6, s8
    addi t6, t6, -1
    and s10, t5, t6
    addi s9, s8, -1
    srl s5, s10, s9
    andi s5, s5, 1
    li s6, 0
    li s9, 2
    blt s8, s9, fa_shift_b_rdone
    addi s9, s8, -2
    srl s6, s10, s9
    andi s6, s6, 1
fa_shift_b_rdone:
    li s7, 0
    li s9, 3
    blt s8, s9, fa_shift_b_sdone
    addi s9, s8, -2
    li t6, 1
    sll t6, t6, s9
    addi t6, t6, -1
    and t6, s10, t6
    sltu s7, zero, t6
fa_shift_b_sdone:
    srl t5, t5, s8
    j fa_addsub
fa_addsub:
    slli t4, t4, 3
    slli t5, t5, 3
    beq s11, zero, fa_27_ready
    li t6, 1
    beq s11, t6, fa_27_shift_a
    slli s5, s5, 2
    slli s6, s6, 1
    or t5, t5, s5
    or t5, t5, s6
    or t5, t5, s7
    j fa_27_ready
fa_27_shift_a:
    slli s5, s5, 2
    slli s6, s6, 1
    or t4, t4, s5
    or t4, t4, s6
    or t4, t4, s7
fa_27_ready:
    bne t0, t1, fa_sub
    add s4, t4, t5
    mv s2, t0
    j fa_norm
fa_sub:
    beq t4, t5, fa_sub_zero
    bltu t5, t4, fa_sub_a_bigger
    sub s4, t5, t4
    mv s2, t1
    j fa_norm
fa_sub_a_bigger:
    sub s4, t4, t5
    mv s2, t0
    j fa_norm
fa_sub_zero:
    li a0, 0
    ret
fa_norm:
    li t6, 134217728
    and t6, s4, t6
    beq t6, zero, fa_norm_left
    andi t6, s4, 1
    slli t6, t6, 1
    or s4, s4, t6
    srli s4, s4, 1
    addi s3, s3, 1
    j fa_round
fa_norm_left:
    li t6, 67108864
    and t6, s4, t6
    bne t6, zero, fa_round
    beq s3, zero, fa_flush
    slli s4, s4, 1
    addi s3, s3, -1
    j fa_norm_left
fa_flush:
    mv a0, s2
    ret
fa_round:
    srli s5, s4, 2
    andi s5, s5, 1
    beq s5, zero, fa_assemble
    srli t6, s4, 1
    andi t6, t6, 1
    andi s9, s4, 1
    or t6, t6, s9
    srli s9, s4, 3
    andi s9, s9, 1
    or t6, t6, s9
    beq t6, zero, fa_assemble
    srli s4, s4, 3
    addi s4, s4, 1
    li t6, 16777216
    and t6, s4, t6
    beq t6, zero, fa_assemble2
    srli s4, s4, 1
    addi s3, s3, 1
    j fa_assemble2
fa_assemble:
    srli s4, s4, 3
fa_assemble2:
    li t6, 255
    bge s3, t6, fa_inf
    bge zero, s3, fa_flush
    slli t6, s3, 23
    or a0, s2, t6
    li t6, 8388607
    and t6, s4, t6
    or a0, a0, t6
    ret
fa_inf:
    li t6, 2139095040
    or a0, s2, t6
    ret
forge_fmul:
    srli t2, a0, 23
    andi t2, t2, 255
    srli t3, a1, 23
    andi t3, t3, 255
    li t6, 8388607
    and t4, a0, t6
    and t5, a1, t6
    or t6, t2, t4
    beq t6, zero, fm_zero
    or t6, t3, t5
    beq t6, zero, fm_zero
    xor s2, a0, a1
    li t6, -2147483648
    and s2, s2, t6
    add s3, t2, t3
    addi s3, s3, -127
    li t6, 8388608
    or t4, t4, t6
    or t5, t5, t6
    mulhu s4, t4, t5
    mul s5, t4, t5
    li t6, 32768
    bltu s4, t6, fm_shift23
    slli s6, s4, 8
    srli t6, s5, 24
    or s6, s6, t6
    li t6, 16777215
    and t6, s5, t6
    srli s7, t6, 23
    andi s7, s7, 1
    srli s8, t6, 22
    andi s8, s8, 1
    li s9, 4194303
    and s9, t6, s9
    sltu s9, zero, s9
    addi s3, s3, 1
    j fm_round
fm_shift23:
    slli s6, s4, 9
    srli t6, s5, 23
    or s6, s6, t6
    li t6, 8388607
    and t6, s5, t6
    srli s7, t6, 22
    andi s7, s7, 1
    srli s8, t6, 21
    andi s8, s8, 1
    li s9, 2097151
    and s9, t6, s9
    sltu s9, zero, s9
fm_round:
    beq s7, zero, fm_assemble
    or t6, s8, s9
    andi s10, s6, 1
    or t6, t6, s10
    beq t6, zero, fm_assemble
    addi s6, s6, 1
    li t6, 16777216
    and t6, s6, t6
    beq t6, zero, fm_assemble
    srli s6, s6, 1
    addi s3, s3, 1
fm_assemble:
    li t6, 255
    bge s3, t6, fm_inf
    bge zero, s3, fm_zero_signed
    slli t6, s3, 23
    or a0, s2, t6
    li t6, 8388607
    and t6, s6, t6
    or a0, a0, t6
    ret
fm_inf:
    li t6, 2139095040
    or a0, s2, t6
    ret
fm_zero:
    xor a0, a0, a1
    li t6, -2147483648
    and a0, a0, t6
    ret
fm_zero_signed:
    mv a0, s2
    ret
