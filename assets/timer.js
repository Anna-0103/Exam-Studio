export default function ({parentElement, data}) {
  const clock = parentElement.querySelector("#clock");
  const caption = parentElement.querySelector("#clock-caption");
  const started = Date.now();
  const update = () => {
    const elapsed = data.elapsed + (data.running ? (Date.now() - started) / 1000 : 0);
    const remaining = Math.max(0, data.duration - elapsed);
    const format = seconds => `${Math.floor(seconds / 60)}:${String(Math.floor(seconds % 60)).padStart(2, "0")}`;
    clock.textContent = format(remaining);
    caption.textContent = remaining === 0 ? "Time is up — you can finish your work." :
      data.running ? "Remaining · timer running" : "Remaining · timer paused";
  };
  update();
  const interval = setInterval(update, 1000);
  return () => clearInterval(interval);
}
