// fwd_txfm_libaom.c — libaom's OWN forward transform, driven from stdin, for scripts/refs/fwd_txfm_ref.py.
//
// The AV1 spec defines only the inverse transform (7.13); the forward one is the encoder's choice. drishti derives
// its forward transform from the spec's inverse (fwd_txfm_ref.py) and this harness is the second implementation it
// is checked against: libaom's av1_fwd_txfm1d.c kernels and its av1_fwd_txfm2d.c driver, compiled from the source in
// ref/ (gitignored; see ref/README.md), not transcribed. The 2D driver is static, so this file #includes its .c.
//
// libaom picks a cosine precision per size (av1_fwd_cos_bit_col / _row: 10 to 13 bits, for int32 headroom); drishti
// computes in i64 and uses the spec's 12-bit Cos128_Lookup everywhere. A COSBIT of 12 forces libaom's 2D driver to
// 12 bits too, which is what makes the two comparable bit for bit; COSBIT 0 keeps libaom's own choice.
//
// Build (fwd_txfm_ref.py --libaom does this):
//   cc -O1 -I ref/aom -I ref/aom-build scripts/refs/fwd_txfm_libaom.c ref/aom-build/libaom.a -lm -lpthread \
//      -o build/fwd_txfm_libaom
//
// Protocol: one request per line, one line of space-separated outputs back.
//   1d KIND N COSBIT v[0..N-1]          KIND 0 = DCT (N 4..64), 1 = ADST (4..16), 2 = identity (4..32)
//   2d TXSZ TXTYPE BD COSBIT v[0..w*h-1] the residual ROW-MAJOR; out[c * h + r], libaom's (transposed) layout
//   wht v[0..15]                        av1_fwht4x4_c on a 4x4 row-major residual; libaom's layout as written

#include <stdio.h>
#include <string.h>

#include "av1/encoder/av1_fwd_txfm2d.c"

void av1_fwht4x4_c(const int16_t *input, tran_low_t *output, int stride);

static TXFM_TYPE kind_type(int kind, int n) {
  if (kind == 0) {
    if (n == 4) return TXFM_TYPE_DCT4;
    if (n == 8) return TXFM_TYPE_DCT8;
    if (n == 16) return TXFM_TYPE_DCT16;
    if (n == 32) return TXFM_TYPE_DCT32;
    if (n == 64) return TXFM_TYPE_DCT64;
  }
  if (kind == 1) {
    if (n == 4) return TXFM_TYPE_ADST4;
    if (n == 8) return TXFM_TYPE_ADST8;
    if (n == 16) return TXFM_TYPE_ADST16;
  }
  if (kind == 2) {
    if (n == 4) return TXFM_TYPE_IDENTITY4;
    if (n == 8) return TXFM_TYPE_IDENTITY8;
    if (n == 16) return TXFM_TYPE_IDENTITY16;
    if (n == 32) return TXFM_TYPE_IDENTITY32;
  }
  return TXFM_TYPE_INVALID;
}

int main(void) {
  char cmd[8];
  static int32_t in32[64], out32[64];
  static int16_t res[64 * 64];
  static int32_t out2d[64 * 64], buf2d[64 * 64];
  int8_t stage_range[MAX_TXFM_STAGE_NUM];
  memset(stage_range, 31, sizeof(stage_range));  // range checks are compiled out (CONFIG_COEFFICIENT_RANGE_CHECKING 0)
  aom_dsp_rtcd();  // av1_round_shift_array and friends are run-time dispatched pointers, NULL until these run
  av1_rtcd();
  while (scanf("%7s", cmd) == 1) {
    if (strcmp(cmd, "1d") == 0) {
      int kind, n, cb;
      if (scanf("%d %d %d", &kind, &n, &cb) != 3) return 2;
      for (int i = 0; i < n; i++) {
        if (scanf("%d", &in32[i]) != 1) return 2;
      }
      TXFM_TYPE t = kind_type(kind, n);
      if (t == TXFM_TYPE_INVALID) return 3;
      fwd_txfm_type_to_func(t)(in32, out32, (int8_t)cb, stage_range);
      for (int i = 0; i < n; i++) printf(i ? " %d" : "%d", out32[i]);
      printf("\n");
    } else if (strcmp(cmd, "2d") == 0) {
      int txsz, txtype, bd, cb;
      if (scanf("%d %d %d %d", &txsz, &txtype, &bd, &cb) != 4) return 2;
      const int w = tx_size_wide[txsz], h = tx_size_high[txsz];
      for (int i = 0; i < w * h; i++) {
        int v;
        if (scanf("%d", &v) != 1) return 2;
        res[i] = (int16_t)v;
      }
      TXFM_2D_FLIP_CFG cfg;
      av1_get_fwd_txfm_cfg((TX_TYPE)txtype, (TX_SIZE)txsz, &cfg);
      if (cb) {
        cfg.cos_bit_col = (int8_t)cb;
        cfg.cos_bit_row = (int8_t)cb;
      }
      fwd_txfm2d_c(res, out2d, w, &cfg, buf2d, bd);
      for (int i = 0; i < w * h; i++) printf(i ? " %d" : "%d", out2d[i]);
      printf("\n");
    } else if (strcmp(cmd, "wht") == 0) {
      tran_low_t o[16];
      for (int i = 0; i < 16; i++) {
        int v;
        if (scanf("%d", &v) != 1) return 2;
        res[i] = (int16_t)v;
      }
      av1_fwht4x4_c(res, o, 4);
      for (int i = 0; i < 16; i++) printf(i ? " %d" : "%d", (int)o[i]);
      printf("\n");
    } else {
      return 4;
    }
    fflush(stdout);
  }
  return 0;
}
