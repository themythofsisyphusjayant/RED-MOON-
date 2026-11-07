/* GPU training loop — Qasida (0.5.0).
 *
 * A full-batch SGD trainer for a 2-layer sigmoid MLP on XOR,
 * with every matmul offloaded to the GPU through
 * forge_cuda_matmul() from kernel.cu (the square-n wrapper
 * verified on Kaggle Tesla T4 in 0.3.0). Elementwise ops
 * (sigmoid, bias add, loss, SGD step) run on the host so
 * this file depends on no unverified kernel.
 *
 * Matrices are padded to square N=4 so the verified
 * wrapper applies directly: X is [batch=4, in=4] (2 real
 * inputs + 2 zero columns), W1 is [in=4, hidden=4],
 * W2 is [hidden=4, out=4] (only column 0 is the output).
 *
 * STATUS — VERIFIED ON A REAL GPU 26 Oct 2026
 * (Kaggle notebook arshhdubeyy/forge-mlp-train v3,
 * Tesla T4, nvcc 12.8.93, private). Two things were
 * needed before it ran: kernel.cu has its own main()
 * (standalone test driver), so it must be compiled
 * alone with -Dmain=forge_kernel_main and linked as
 * an object, not compiled together with this file
 * (v1 failed at link with "multiple definition of
 * main"); and LR 0.5 does NOT learn in 2000 epochs
 * (v2 on GPU: loss pinned at 0.25, predictions all
 * ~0.5 — the mean-predictor saddle, confirmed by a
 * CPU mirror reproducing the GPU numbers exactly).
 * At LR 5.0 (v3, this file's value) it learns:
 * epoch 0 loss 0.253864, 500: 0.248944,
 * 1000: 0.005385, 1500: 0.001529, predictions
 * 0.028651 0.972222 0.967339 0.027646 (~0, 1, 1, 0).
 * This VM has no nvcc and no GPU, so this file
 * cannot run here; on a CUDA machine, compile
 * kernel.cu alone first (renaming its main), then
 * link: nvcc -O2 mlp_train.cu kernel.o -o mlp_train
 */

#include <stdio.h>
#include <stdlib.h>
#include <math.h>

void forge_cuda_matmul(const double *a, const double *b, double *out, long long n);

#define N 4
#define EPOCHS 2000
#define LR 5.0

static double sigmoid(double x) { return 1.0 / (1.0 + exp(-x)); }

static void transpose4(const double *a, double *out) {
    for (int r = 0; r < N; r++)
        for (int c = 0; c < N; c++)
            out[c * N + r] = a[r * N + c];
}

static void add_bias(double *m, const double *bias, int cols_used) {
    for (int r = 0; r < N; r++)
        for (int c = 0; c < cols_used; c++)
            m[r * N + c] += bias[c];
}

int main(void) {
    /* XOR: rows are samples, columns 0-1 are inputs. */
    double X[N * N] = {0, 0, 0, 0,
                       0, 1, 0, 0,
                       1, 0, 0, 0,
                       1, 1, 0, 0};
    double Y[N] = {0, 1, 1, 0};
    /* Deterministic init (same spirit as the CPU XOR trainer). */
    double W1[N * N] = {0.5, -0.3, 0.2, 0.1,
                        -0.4, 0.6, -0.1, 0.3,
                        0, 0, 0, 0,
                        0, 0, 0, 0};
    double b1[N] = {0.1, -0.1, 0.05, 0.0};
    double W2[N * N] = {0.7, 0, 0, 0,
                        -0.5, 0, 0, 0,
                        0.3, 0, 0, 0,
                        -0.2, 0, 0, 0};
    double b2 = 0.05;
    double H[N * N], Hsig[N * N], O[N * N], tmp[N * N], tmpT[N * N];
    double dO[N], dH[N * N], gW2[N * N], gW1[N * N], gb1[N], gb2;
    for (int epoch = 0; epoch < EPOCHS; epoch++) {
        /* Forward: H = sigmoid(X @ W1 + b1); O = H @ W2 + b2. */
        forge_cuda_matmul(X, W1, H, N);
        for (int i = 0; i < N * N; i++) Hsig[i] = 0.0;
        for (int r = 0; r < N; r++)
            for (int c = 0; c < N; c++)
                Hsig[r * N + c] = sigmoid(H[r * N + c] + b1[c]);
        forge_cuda_matmul(Hsig, W2, O, N);
        double loss = 0.0;
        for (int r = 0; r < N; r++) {
            double o = sigmoid(O[r * N] + b2);
            double d = o - Y[r];
            loss += d * d;
            dO[r] = d * o * (1.0 - o);
        }
        loss /= N;
        if (epoch % 500 == 0) printf("epoch %d loss = %f\n", epoch, loss);
        /* Backward: gW2 = Hsig^T @ dO (dO as a [4,4] matrix
         * with only column 0 filled); dH = dO @ W2^T .* sig'. */
        double dOm[N * N] = {0};
        for (int r = 0; r < N; r++) dOm[r * N] = dO[r];
        transpose4(Hsig, tmpT);
        forge_cuda_matmul(tmpT, dOm, gW2, N);
        transpose4(W2, tmpT);
        forge_cuda_matmul(dOm, tmpT, tmp, N);
        gb2 = 0.0;
        for (int r = 0; r < N; r++) gb2 += dO[r];
        for (int r = 0; r < N; r++) {
            for (int c = 0; c < N; c++) {
                double s = Hsig[r * N + c];
                dH[r * N + c] = tmp[r * N + c] * s * (1.0 - s);
            }
        }
        transpose4(X, tmpT);
        forge_cuda_matmul(tmpT, dH, gW1, N);
        for (int c = 0; c < N; c++) {
            gb1[c] = 0.0;
            for (int r = 0; r < N; r++) gb1[c] += dH[r * N + c];
        }
        /* SGD step (full batch, gradients already summed
         * over the 4 samples; scale by 1/N like the mean). */
        for (int i = 0; i < N * N; i++) {
            W2[i] -= LR * gW2[i] / N;
            W1[i] -= LR * gW1[i] / N;
        }
        for (int c = 0; c < N; c++) b1[c] -= LR * gb1[c] / N;
        b2 -= LR * gb2 / N;
    }
    forge_cuda_matmul(X, W1, H, N);
    for (int r = 0; r < N; r++)
        for (int c = 0; c < N; c++)
            Hsig[r * N + c] = sigmoid(H[r * N + c] + b1[c]);
    forge_cuda_matmul(Hsig, W2, O, N);
    printf("predictions:");
    for (int r = 0; r < N; r++)
        printf(" %f", sigmoid(O[r * N] + b2));
    printf("\n");
    return 0;
}
