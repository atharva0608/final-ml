# verify_onnx_local.py
import lightgbm as lgb
import numpy as np
import onnxruntime as rt
from onnxconverter_common.data_types import FloatTensorType
from onnxmltools.convert import convert_lightgbm


def sanity_check():
    print("🚀 Starting Local Math Verification...")

    # 1. Simulate the Pipeline (Dummy Data)
    # Ensure float32 for consistency
    X = np.random.rand(100, 5).astype(np.float32)
    y = np.random.rand(100).astype(np.float32)
    train_data = lgb.Dataset(X, label=y)

    # 2. Train (Native API)
    model = lgb.train({"objective": "regression", "verbose": -1}, train_data, 10)

    # 3. Simulate Your "Dynamic Shape" Logic
    n_features = model.num_feature()
    initial_types = [("input", FloatTensorType([None, n_features]))]

    # 4. Export (Opset 14)
    onnx_model = convert_lightgbm(model, initial_types=initial_types, target_opset=14)
    onnx_bytes = onnx_model.SerializeToString()

    # 5. Inference Comparison
    sess = rt.InferenceSession(onnx_bytes)
    # Note: ONNX Runtime is strict about float32
    onnx_pred = sess.run(None, {"input": X[:1].astype(np.float32)})[0]
    lgb_pred = model.predict(X[:1])

    # 6. Verify
    # Flatten ONNX output if necessary (sometimes it is [1, 1])
    onnx_val = onnx_pred.flatten()[0]
    lgb_val = lgb_pred[0]

    diff = np.abs(onnx_val - lgb_val)
    print(f"   LGBM Pred: {lgb_val:.9f}")
    print(f"   ONNX Pred: {onnx_val:.9f}")
    print(f"   Max Difference: {diff:.9f}")

    if diff < 1e-5:
        print("✅ PASSED: Math is accurate.")
    else:
        print("❌ FAILED: Predictions diverge.")


if __name__ == "__main__":
    sanity_check()
