import os
os.environ["TF_CPP_MIN_LOG_LEVEL"] = "2"  # menos advertencias

import numpy as np
import tensorflow as tf

# 1. Cargar los datos
(x_train, y_train), (x_test, y_test) = tf.keras.datasets.mnist.load_data()

# 2. Normalizar: pasar los píxeles de 0-255 a 0-1 (la red aprende mejor así)
x_train = x_train / 255.0
x_test = x_test / 255.0

# 3. Definir el modelo
modelo = tf.keras.Sequential([
    tf.keras.layers.Input(shape=(28, 28)),
    tf.keras.layers.Flatten(),                      # imagen 28x28 -> vector de 784
    tf.keras.layers.Dense(256, activation="relu"),  # capa oculta
    tf.keras.layers.Dropout(0.2),                   # evita memorizar
    tf.keras.layers.Dense(10, activation="softmax") # una salida por dígito (0-9)
])

modelo.compile(
    optimizer="adam",
    loss="sparse_categorical_crossentropy",
    metrics=["accuracy"]
)

# 4. Entrenar
modelo.fit(x_train, y_train, epochs=10, validation_split=0.1)

# 5. Evaluar con las 10,000 imágenes de prueba
perdida, precision = modelo.evaluate(x_test, y_test, verbose=0)
print(f"\nPrecisión en datos de prueba: {precision:.4f}")

# 6. Predecir una imagen concreta
indice = 0
prediccion = modelo.predict(x_test[indice:indice + 1], verbose=0)
print("Número real:", y_test[indice])
print("Número predicho:", np.argmax(prediccion))

import matplotlib.pyplot as plt

plt.figure(figsize=(10, 4))
for i in range(10):
    plt.subplot(2, 5, i + 1)
    plt.imshow(x_test[i], cmap="gray")
    pred = np.argmax(modelo.predict(x_test[i:i + 1], verbose=0))
    plt.title(f"Real: {y_test[i]} / Pred: {pred}")
    plt.axis("off")
plt.tight_layout()
plt.show()

predicciones = np.argmax(modelo.predict(x_test, verbose=0), axis=1)
matriz = tf.math.confusion_matrix(y_test, predicciones).numpy()

fig = plt.figure(figsize=(8, 7))
ax = fig.add_subplot(projection="3d")

X, Y = np.meshgrid(range(10), range(10))
ax.bar3d(X.ravel(), Y.ravel(), 0, 0.8, 0.8, matriz.ravel(), shade=True)

ax.set_xlabel("Predicho")
ax.set_ylabel("Real")
ax.set_zlabel("Cantidad")
ax.set_title("Matriz de confusión MNIST")
plt.show()