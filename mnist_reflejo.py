import os
os.environ["TF_CPP_MIN_LOG_LEVEL"] = "2"

import numpy as np
import tensorflow as tf
import matplotlib.pyplot as plt

TIPO = "espejo"   # cambia a "agua" para el reflejo en el agua

(x_train, _), (x_test, _) = tf.keras.datasets.mnist.load_data()
x_train = x_train / 255.0
x_test = x_test / 255.0

def reflejo(img):
    if TIPO == "espejo":
        return np.flip(img, axis=2)            # izquierda <-> derecha
    else:
        return np.flip(img, axis=1) * 0.5      # arriba <-> abajo y más tenue

# Entrada: imagen original. Objetivo: su reflejo
y_train = reflejo(x_train)
y_test = reflejo(x_test)

modelo = tf.keras.Sequential([
    tf.keras.layers.Input(shape=(28, 28)),
    tf.keras.layers.Flatten(),
    tf.keras.layers.Dense(256, activation="relu"),
    tf.keras.layers.Dense(256, activation="relu"),
    tf.keras.layers.Dense(784, activation="sigmoid"),
    tf.keras.layers.Reshape((28, 28)),
])
modelo.compile(optimizer="adam", loss="mse")
modelo.fit(x_train, y_train, epochs=10, batch_size=256, validation_split=0.1)

generadas = modelo.predict(x_test[:8], verbose=0)

filas = [("Original", x_test), ("Reflejo de la red", generadas), ("Reflejo real", y_test)]
plt.figure(figsize=(12, 5))
for f, (nombre, datos) in enumerate(filas):
    for i in range(8):
        plt.subplot(3, 8, f * 8 + i + 1)
        plt.imshow(datos[i], cmap="gray", vmin=0, vmax=1)
        plt.axis("off")
        if i == 0:
            plt.title(nombre, fontsize=8, loc="left")
plt.tight_layout()
plt.show()