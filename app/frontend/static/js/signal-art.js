// Keep the original toroidal coil and pass one spring pulse from rib to rib.
const canvas = document.getElementById('signal-art');

if (canvas) {
    const context = canvas.getContext('2d');
    const motion = window.matchMedia('(prefers-reduced-motion: reduce)');
    const count = 136;
    const tau = Math.PI * 2;
    const duration = 11000;
    let ribs = [];
    let width = 0;
    let height = 0;
    let frame = 0;
    let lastPaint = 0;

    function point(t, v, scale, centerX, centerY) {
        const radius = 1 + 0.43 * Math.cos(v);
        const x = radius * Math.cos(t);
        const y = radius * Math.sin(t);
        const z = 0.43 * Math.sin(v) + 0.22 * Math.sin(2 * t);
        const a = x * 0.86 + z * 0.51;
        const b = y * 0.68 - (-x * 0.51 + z * 0.86) * 0.735;
        return {
            x: (a * 0.89 + b * 0.455) * scale + centerX,
            y: (-a * 0.455 + b * 0.89) * scale + centerY,
            depth: y * 0.735 + (-x * 0.51 + z * 0.86) * 0.68
        };
    }

    function rebuild() {
        width = canvas.clientWidth;
        height = canvas.clientHeight;
        if (!width || !height) return;
        const ratio = Math.min(window.devicePixelRatio || 1, 2);
        canvas.width = Math.round(width * ratio);
        canvas.height = Math.round(height * ratio);
        context.setTransform(ratio, 0, 0, ratio, 0, 0);
        const scale = Math.min(width * 0.28, height * 0.33);
        ribs = [];

        for (let index = 0; index < count; index += 1) {
            const angle = tau * index / count;
            const path = new Path2D();
            const outer = new Path2D();
            let depth = 0;

            for (let step = 0; step <= 70; step += 1) {
                const p = point(angle, tau * step / 70, scale, width / 2, height / 2);
                if (step === 0) path.moveTo(p.x, p.y);
                else path.lineTo(p.x, p.y);
                depth += p.depth / 71;
            }
            for (let step = 0; step <= 70; step += 1) {
                const p = point(angle, -Math.PI / 2 + Math.PI * step / 70, scale, width / 2, height / 2);
                if (step === 0) outer.moveTo(p.x, p.y);
                else outer.lineTo(p.x, p.y);
            }

            const center = point(angle, 0, scale, width / 2, height / 2);
            const outwardX = center.x - width / 2;
            const outwardY = center.y - height / 2;
            const outwardLength = Math.hypot(outwardX, outwardY) || 1;
            ribs.push({path, outer, depth, angle, index,
                outwardX: outwardX / outwardLength,
                outwardY: outwardY / outwardLength});
        }
        ribs.sort((a, b) => a.depth - b.depth);
    }

    function draw(timestamp = 0) {
        if (!motion.matches && timestamp - lastPaint < 40) {
            frame = requestAnimationFrame(draw);
            return;
        }
        lastPaint = timestamp;
        context.clearRect(0, 0, width, height);
        const head = timestamp / duration * count % count;

        for (const rib of ribs) {
            // Only the most recently reached ribs move; each returns to rest
            // before the next part of the coil is reached.
            const behind = (head - rib.index + count) % count;
            const spring = !motion.matches && behind < 8
                ? Math.sin(behind / 8 * Math.PI) ** 2
                : 0;
            context.save();
            context.translate(rib.outwardX * spring * 4, rib.outwardY * spring * 4);
            const light = 0.5 + 0.5 * Math.cos(rib.angle + 1.2);
            context.fillStyle = '#183c29';
            context.fill(rib.path);
            context.strokeStyle = `hsl(${76 + light * 8} 91% ${41 + light * 35}%)`;
            context.lineWidth = 1.35;
            context.stroke(rib.path);

            if (spring > 0) {
                context.strokeStyle = `rgba(218, 255, 139, ${0.45 + spring * 0.55})`;
                context.lineWidth = 1.4 + spring * 2;
                context.shadowColor = `rgba(205, 255, 112, ${spring * 0.8})`;
                context.shadowBlur = spring * 12;
                context.stroke(rib.outer);
            }
            context.restore();
        }
        if (!motion.matches) frame = requestAnimationFrame(draw);
    }

    new ResizeObserver(() => {
        cancelAnimationFrame(frame);
        rebuild();
        draw();
    }).observe(canvas);
    motion.addEventListener('change', () => {
        cancelAnimationFrame(frame);
        lastPaint = 0;
        draw();
    });
}
