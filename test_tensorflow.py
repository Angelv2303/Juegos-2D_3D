import tensorflow as tf
import numpy as np

print("Versión de TensorFlow:", tf.__version__)

a = tf.constant([[1, 2], [3, 4]])
b = tf.constant([[5, 6], [7, 8]])
print("Suma:\n", tf.add(a, b).numpy())
print("Multiplicación de matrices:\n", tf.matmul(a, b).numpy())

print("GPUs disponibles:", tf.config.list_physical_devices("GPU"))

x = np.array([1, 2, 3, 4, 5], dtype=float)
y = np.array([2, 4, 6, 8, 10], dtype=float)  # y = 2x

modelo = tf.keras.Sequential([
    tf.keras.layers.Input(shape=(1,)),
    tf.keras.layers.Dense(1)
])
modelo.compile(optimizer="sgd", loss="mse")
modelo.fit(x, y, epochs=200, verbose=0)

print("Predicción para x=10 (debería ser cercana a 20):",
      modelo.predict(np.array([10.0]), verbose=0)[0][0])