# Nimbus-Inference on the sopa image. --no-deps because Nimbus pins numpy<2 but runs on numpy 2.
FROM docker.io/josenimo/sopa:2.3.0

RUN pip install --no-cache-dir --no-deps Nimbus-Inference==0.0.5 \
    && pip install --no-cache-dir --no-deps \
        alpineer==0.2.1 kornia==0.9.0 pyometiff==1.1.4 lmdb==3.0.0 lxml==5.4.0 \
    && pip install --no-cache-dir huggingface_hub==2.4.0

# V1.pt is baked in so no run needs the network (MIT licence, ungated).
RUN python -c "import pathlib, nimbus_inference as n; from huggingface_hub import hf_hub_download; \
d = pathlib.Path(n.__file__).parent / 'assets'; d.mkdir(exist_ok=True); \
hf_hub_download('JLrumberger/Nimbus-Inference', 'V1.pt', local_dir=d)"

ENV HF_HUB_OFFLINE=1
