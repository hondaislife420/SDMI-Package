// Free-N / parameterized multi-job skin.
// t0 bones, t1 weights, t2 rest tans, t3 rest pos
// t5 JobParams: uint base, count, wbase, pad
// u0 out tan (half4 pairs), u1 out pos (float xyz)
// Hard cap MAX_VERTS — raise only with matching RW buffer sizes in mod.ini

#define MAX_VERTS 16384

Buffer<float4> Bones : register(t0);
Buffer<uint> Weights : register(t1);
Buffer<float4> RestTangents : register(t2);
Buffer<float> RestPos : register(t3);
Buffer<uint> JobParams : register(t5);

RWBuffer<float4> OutTan : register(u0);
RWBuffer<float> OutPos : register(u1);

void AccumBone(uint boneIndex, float w, inout float4 row0, inout float4 row1, inout float4 row2)
{
	uint b = boneIndex * 3;
	row0 += Bones[b + 0] * w;
	row1 += Bones[b + 1] * w;
	row2 += Bones[b + 2] * w;
}

[numthreads(64, 1, 1)]
void main(uint3 dtid : SV_DispatchThreadID)
{
	uint base = JobParams[0];
	uint count = JobParams[1];
	uint wbase = JobParams[2];

	uint i = dtid.x;
	if (i >= count)
		return;

	uint vid = base + i;
	if (vid >= MAX_VERTS)
		return;

	uint widx = wbase + i * 2;
	uint boneWord = Weights[widx + 0];
	uint weightWord = Weights[widx + 1];

	uint b0 = (boneWord >> 0) & 0xff;
	uint b1 = (boneWord >> 8) & 0xff;
	uint b2 = (boneWord >> 16) & 0xff;
	uint b3 = (boneWord >> 24) & 0xff;

	float w0 = ((weightWord >> 0) & 0xff) * (1.0 / 255.0);
	float w1 = ((weightWord >> 8) & 0xff) * (1.0 / 255.0);
	float w2 = ((weightWord >> 16) & 0xff) * (1.0 / 255.0);
	float w3 = ((weightWord >> 24) & 0xff) * (1.0 / 255.0);

	float wsum = w0 + w1 + w2 + w3;
	if (wsum < 1e-6)
	{
		w0 = 1.0;
		w1 = w2 = w3 = 0.0;
		wsum = 1.0;
	}
	float inv = 1.0 / wsum;
	w0 *= inv;
	w1 *= inv;
	w2 *= inv;
	w3 *= inv;

	float4 row0 = 0;
	float4 row1 = 0;
	float4 row2 = 0;
	AccumBone(b0, w0, row0, row1, row2);
	AccumBone(b1, w1, row0, row1, row2);
	AccumBone(b2, w2, row0, row1, row2);
	AccumBone(b3, w3, row0, row1, row2);

	uint pidx = vid * 3;
	float4 pref = float4(RestPos[pidx + 0], RestPos[pidx + 1], RestPos[pidx + 2], 1.0);

	OutPos[pidx + 0] = dot(row0, pref);
	OutPos[pidx + 1] = dot(row1, pref);
	OutPos[pidx + 2] = dot(row2, pref);

	uint tidx = vid * 2;
	float3 T = RestTangents[tidx + 0].xyz;
	float3 B = RestTangents[tidx + 1].xyz;
	float3x3 R = float3x3(row0.xyz, row1.xyz, row2.xyz);
	float3 Ts = mul(R, T);
	float3 Bs = mul(R, B);
	float tLen = length(Ts);
	float bLen = length(Bs);
	if (tLen > 1e-8)
		Ts /= tLen;
	if (bLen > 1e-8)
		Bs /= bLen;
	OutTan[tidx + 0] = float4(Ts, RestTangents[tidx + 0].w);
	OutTan[tidx + 1] = float4(Bs, RestTangents[tidx + 1].w);
}
