import numpy as np
import matplotlib.pyplot as plt
import tensorflow as tf

(x_train, y_train), (x_test, y_test) = tf.keras.datasets.mnist.load_data()

# Busca el primer 5 del conjunto de prueba
indice = np.where(y_test == 5)[0][0]
imagen = x_test[indice] / 255.0

X, Y = np.meshgrid(range(28), range(28))

fig = plt.figure(figsize=(8, 7))
ax = fig.add_subplot(projection="3d")
ax.plot_surface(X, Y, imagen, cmap="turbo")
ax.set_title("MNIST 3D - Numero 5")
ax.set_xlabel("Columna")
ax.set_ylabel("Fila")
ax.set_zlabel("Intensidad")
plt.show()